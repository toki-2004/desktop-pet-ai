package com.toki.petchat;

import android.app.Activity;
import android.graphics.Color;
import android.net.http.SslError;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
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
 * 桌宠聊天记录网页的入口：两个按钮，点哪个就用 WebView 打开哪个地址。
 *
 * 换地址 / 换口令（config.json 的 webchat_token）时改下面 URLS 再重新打包，
 * 打包命令见 android/build_apk.cmd。
 */
public class MainActivity extends Activity {

    /** 按钮文案与对应地址（结尾 ?k= 是桌宠聊天网页的访问口令） */
    private static final String[] LABELS = {"地址1", "地址2"};
    private static final String[] URLS = {
            "http://172.42.50.38:8848/?k=ee499a5c",   // 局域网直连
            "https://frp-off.com:56794/?k=ee499a5c",  // frp 外网隧道
    };

    private WebView webView;
    private LinearLayout menu;

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
                // 地址2 走 SakuraFrp 隧道，证书是该域名下的自签名证书，不放行会白屏。
                // 信任边界就是上面写死的两个地址，不存在用户可输入其它站点的情况。
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
        return view;
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
