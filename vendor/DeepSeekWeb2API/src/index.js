import http from 'node:http';
import { URL } from 'node:url';
import fs from 'node:fs/promises';
import { config } from './config.js';
import { DeepSeekClient } from './deepseekClient.js';
import { logger } from './logger.js';
import { Mutex } from './mutex.js';
import { parseChatRequest, cleanupFiles } from './parser.js';
import { listModels, resolveModel } from './models.js';
import {
  ApiError,
  completionResponse,
  contentChunk,
  done,
  error,
  heartbeat,
  json,
  requestId,
  roleChunk,
  sse,
  sseHeaders
} from './http.js';

const client = new DeepSeekClient(config);
const mutex = new Mutex();

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

if (config.loginMode) {
  await client.login();
} else {
  await fs.mkdir(config.tempDir, { recursive: true });
  const server = http.createServer(handleRequest);
  server.listen(config.port, config.host, () => {
    logger.info('DeepSeekWeb2API started', {
      url: config.publicBaseUrl || `http://${config.host}:${config.port}`,
      auth: config.apiKey ? 'enabled' : 'disabled'
    });
  });
}

async function shutdown() {
  logger.info('shutting down');
  await client.close();
  process.exit(0);
}

async function handleRequest(req, res) {
  const parsedUrl = new URL(req.url || '/', `http://${req.headers.host || 'localhost'}`);

  try {
    if (req.method === 'GET' && parsedUrl.pathname === '/health') {
      json(res, 200, { ok: true, queue: mutex.size });
      return;
    }

    if (parsedUrl.pathname.startsWith('/v1/')) {
      authorize(req);
    }

    if (req.method === 'GET' && parsedUrl.pathname === '/v1/models') {
      json(res, 200, listModels());
      return;
    }

    if (req.method === 'POST' && parsedUrl.pathname === '/v1/chat/completions') {
      await handleChatCompletions(req, res);
      return;
    }

    json(res, 404, { error: { message: 'Not found', type: 'invalid_request_error', code: 'not_found' } });
  } catch (err) {
    logger.error('request failed', { error: err.message });
    error(res, err);
  }
}

function authorize(req) {
  if (!config.apiKey) return;
  const header = req.headers.authorization || '';
  const token = header.startsWith('Bearer ') ? header.slice(7) : '';
  if (token !== config.apiKey) {
    throw new ApiError('Invalid API key', 401, 'invalid_api_key', 'authentication_error');
  }
}

async function readJson(req) {
  const chunks = [];
  let total = 0;

  for await (const chunk of req) {
    total += chunk.length;
    if (total > config.maxBodyBytes) {
      throw new ApiError('Request body is too large', 413, 'request_too_large', 'invalid_request_error');
    }
    chunks.push(chunk);
  }

  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf8'));
  } catch {
    throw new ApiError('Request body must be valid JSON', 400, 'invalid_json', 'invalid_request_error');
  }
}

async function handleChatCompletions(req, res) {
  const body = await readJson(req);
  const parsed = await parseChatRequest(body, config);
  const model = resolveModel(parsed.requestedModel);
  if (!model) {
    await cleanupFiles(parsed.imagePaths);
    throw new ApiError(`Model is not supported: ${parsed.requestedModel}`, 400, 'model_not_found', 'invalid_request_error');
  }

  const id = requestId();
  if (parsed.stream) {
    await handleStreaming(res, id, model.id, async onDelta => {
      try {
        return await client.generate({
          prompt: parsed.prompt,
          imagePaths: parsed.imagePaths,
          model,
          onDelta
        });
      } finally {
        await cleanupFiles(parsed.imagePaths);
      }
    });
    return;
  }

  const run = async () => {
    try {
      return await client.generate({
        prompt: parsed.prompt,
        imagePaths: parsed.imagePaths,
        model
      });
    } finally {
      await cleanupFiles(parsed.imagePaths);
    }
  };

  const result = await mutex.run(run);
  json(res, 200, completionResponse({
    id,
    model: model.id,
    content: result.text,
    reasoning: result.reasoning
  }));
}

async function handleStreaming(res, id, modelId, runWithDelta) {
  sseHeaders(res);
  sse(res, roleChunk({ id, model: modelId }));
  const keepalive = setInterval(() => heartbeat(res), config.keepaliveMs);
  let emitted = false;

  const onDelta = delta => {
    if (res.writableEnded || !delta?.value) return;
    emitted = true;
    if (delta.type === 'reasoning') {
      sse(res, contentChunk({ id, model: modelId, reasoning: delta.value }));
    } else {
      sse(res, contentChunk({ id, model: modelId, content: delta.value }));
    }
  };

  try {
    const result = await mutex.run(() => runWithDelta(onDelta));
    if (!emitted && result.reasoning) {
      sse(res, contentChunk({ id, model: modelId, reasoning: result.reasoning }));
    }
    if (!emitted && result.text) {
      sse(res, contentChunk({ id, model: modelId, content: result.text }));
    }
    sse(res, contentChunk({ id, model: modelId, finishReason: 'stop' }));
    done(res);
  } catch (err) {
    error(res, err, true);
  } finally {
    clearInterval(keepalive);
  }
}
