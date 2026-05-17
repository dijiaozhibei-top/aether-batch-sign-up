# 手动获取 Turnstile Token

## 方法一：浏览器控制台（推荐）

1. 打开 Chrome/Edge，访问 https://to-aether.com/register
2. 按 `F12` 打开开发者工具
3. 切换到 **Console（控制台）** 标签
4. **粘贴并运行** 以下 JavaScript：

```javascript
// 等待 Turnstile 库加载
function waitForTurnstile(callback) {
  if (typeof turnstile !== 'undefined') return callback();
  setTimeout(() => waitForTurnstile(callback), 500);
}

waitForTurnstile(() => {
  // 创建隐藏输入
  let inp = document.querySelector('input[name="cf-turnstile-response"]');
  if (!inp) {
    inp = document.createElement('input');
    inp.type = 'hidden';
    inp.name = 'cf-turnstile-response';
    document.body.appendChild(inp);
  }

  // 渲染 Turnstile
  turnstile.render(inp, {
    sitekey: '0x4AAAAAACzc2OvvV_ueC81i',
    callback: function(token) {
      inp.value = token;
      console.log('===== TURNSTILE TOKEN START =====');
      console.log(token);
      console.log('===== TURNSTILE TOKEN END =====');
      console.log('有效期约5分钟，尽快使用');
    },
    'error-callback': function(e) {
      console.error('Turnstile error:', JSON.stringify(e));
    }
  });

  // 执行挑战
  setTimeout(() => {
    turnstile.execute(inp);
    console.log('Turnstile 挑战已触发，请完成验证...');
  }, 1000);
});
```

5. 页面右上角会显示 Turnstile 验证（一个复选框 "I am human"）
6. **点击复选框**完成验证
7. 控制台会输出 token（以 `0.` 开头的一长串字符）
8. **复制 token**

## 设置到 GitHub Secrets

1. 打开 https://github.com/dijiaozhibei-top/aether-batch-sign-up/settings/secrets/actions
2. 点击 **"New repository secret"**
3. Name: `TURNSTILE_TOKEN`
4. Secret: 粘贴你复制的 token
5. 点击 **"Add secret"**
6. 回到 Actions 页面，手动触发 workflow

> Token 有效期约 5 分钟，请尽快触发 workflow。一个 token 可以用于多个账户注册。

## 获取新 Token

每次触发 workflow 前都需要重新获取 token（因为旧的已过期）。重复以上步骤即可。
