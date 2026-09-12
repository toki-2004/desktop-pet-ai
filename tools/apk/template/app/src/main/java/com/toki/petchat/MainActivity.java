package com.toki.petchat;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.net.http.SslError;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.SslErrorHandler;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

/**
 * 桌宠聊天记录网页的入口：一个按钮，点开就用 WebView 打开预置地址。
 *
 * URL 与按钮文案由 tools/apk/build_apk.ps1 在打包时填进来（占位符 __URL__ / __LABEL__），
 * 所以这个模板里不含任何个人地址。
 */
public class MainActivity extends Activity {

    private static final int REQ_FILE = 1001;

    private static final String[] LABELS = {"__LABEL__"};
    private static final String[] URLS = {"__URL__"};

    private WebView webView;
    private LinearLayout menu;
    private ValueCallback<Uri[]> fileCallback;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        FrameLayout root = new FrameLayout(this);
        menu = buildMenu();
        webView = buildWebView();
        webView.setVisibility(View.GONE);
        root.addView(menu);
        root.addView(webView);
        setContentView(root);
    }

    private LinearLayout buildMenu() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setGravity(Gravity.CENTER);
        box.setBackgroundColor(Color.parseColor("#10141C"));
        box.setPadding(64, 64, 64, 64);

        TextView title = new TextView(this);
        title.setText(R.string.app_name);
        title.setTextColor(Color.WHITE);
        title.setTextSize(24);
        title.setGravity(Gravity.CENTER);
        box.addView(title);

        for (int i = 0; i < LABELS.length; i++) {
            final String url = URLS[i];
            Button button = new Button(this);
            button.setText(LABELS[i]);
            button.setTextSize(18);
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
            lp.topMargin = 28;
            button.setLayoutParams(lp);
            button.setOnClickListener(v -> open(url));
            box.addView(button);
        }
        return box;
    }

    private WebView buildWebView() {
        WebView view = new WebView(this);
        WebSettings settings = view.getSettings();
        settings.setJavaScriptEnabled(true);   // 页面靠 JS 轮询记录、发消息
        settings.setDomStorageEnabled(true);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        view.setWebViewClient(new WebViewClient() {
            @Override
            public void onReceivedSslError(WebView v, SslErrorHandler handler, SslError error) {
                // 自建/隧道地址常是自签名证书，不放行会白屏；信任边界就是这个预置地址
                handler.proceed();
            }

            @Override
            public void onReceivedError(WebView v, WebResourceRequest request,
                                        WebResourceError error) {
                if (request != null && request.isForMainFrame()) {
                    Toast.makeText(MainActivity.this,
                            "打不开：确认桌宠在运行、手机和它同一个网络",
                            Toast.LENGTH_LONG).show();
                }
            }
        });
        // 没有 WebChromeClient.onShowFileChooser，页面里的 <input type="file"> 点了没反应
        view.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView v, ValueCallback<Uri[]> callback,
                                             FileChooserParams params) {
                if (fileCallback != null) {
                    fileCallback.onReceiveValue(null);
                }
                fileCallback = callback;
                try {
                    Intent intent = params.createIntent();
                    intent.addCategory(Intent.CATEGORY_OPENABLE);
                    startActivityForResult(intent, REQ_FILE);
                    return true;
                } catch (Exception e) {
                    fileCallback = null;
                    Toast.makeText(MainActivity.this, "打不开文件选择器", Toast.LENGTH_SHORT).show();
                    return false;
                }
            }
        });
        return view;
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == REQ_FILE) {
            Uri[] result = null;
            if (resultCode == RESULT_OK && data != null) {
                if (data.getClipData() != null) {
                    int n = data.getClipData().getItemCount();
                    result = new Uri[n];
                    for (int i = 0; i < n; i++) {
                        result[i] = data.getClipData().getItemAt(i).getUri();
                    }
                } else if (data.getData() != null) {
                    result = new Uri[]{data.getData()};
                }
            }
            if (fileCallback != null) {
                fileCallback.onReceiveValue(result);
                fileCallback = null;
            }
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    private void open(String url) {
        Toast.makeText(this, "正在打开…", Toast.LENGTH_SHORT).show();
        menu.setVisibility(View.GONE);
        webView.setVisibility(View.VISIBLE);
        webView.loadUrl(url);
    }

    @Override
    public void onBackPressed() {
        if (webView.getVisibility() == View.VISIBLE) {
            webView.stopLoading();
            webView.loadUrl("about:blank");   // 断开轮询，别在后台一直刷
            webView.setVisibility(View.GONE);
            menu.setVisibility(View.VISIBLE);
            return;
        }
        super.onBackPressed();
    }
}
