import { cli, Strategy } from '@jackwener/opencli/registry';
/**
 * 发布即刻动态
 *
 * 即刻首页 /following 顶部有内联发帖框（"分享你的想法..."），
 * 直接在其中输入文本，点击"发送"按钮即可发布。
 */
cli({
    site: 'jike',
    name: 'create',
    access: 'write',
    description: '发布即刻动态',
    domain: 'web.okjike.com',
    strategy: Strategy.UI,
    browser: true,
    args: [
        { name: 'text', type: 'string', required: true, positional: true, help: '动态正文内容' },
        // 本机补丁 2026-09-13：配图 + 只填不发
        { name: 'images', type: 'string', required: false, help: '图片路径，逗号分隔（jpg/png）' },
        { name: 'dry-run', type: 'bool', default: false, help: '只填好正文和图片、核验后清空，不点发送' },
    ],
    columns: ['status', 'message'],
    func: async (page, kwargs) => {
        // 1. 导航到首页（有内联发帖框）
        await page.goto('https://web.okjike.com');
        const imagePaths = kwargs.images ? String(kwargs.images).split(',').map((s) => s.trim()).filter(Boolean) : [];
        if (imagePaths.length) {
            const fs = await import('node:fs');
            const path = await import('node:path');
            const files = imagePaths.map((p) => {
                const abs = path.default.resolve(p);
                if (!fs.default.existsSync(abs)) throw new Error(`Image not found: ${abs}`);
                return { name: path.default.basename(abs), type: abs.endsWith('.png') ? 'image/png' : 'image/jpeg', b64: fs.default.readFileSync(abs).toString('base64') };
            });
            await page.wait(2);
            const inj = await page.evaluate(`(() => {
        const form = document.querySelector('[class*="_postForm_"]');
        const input = form && form.querySelector('input[type="file"]');
        if (!input) return { ok: false, message: '未找到发帖框图片输入' };
        const dt = new DataTransfer();
        for (const f of ${JSON.stringify(files)}) {
          const bin = atob(f.b64); const arr = new Uint8Array(bin.length);
          for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
          dt.items.add(new File([arr], f.name, { type: f.type }));
        }
        input.files = dt.files;
        input.dispatchEvent(new Event('change', { bubbles: true }));
        return { ok: true };
      })()`);
            if (!inj.ok) return [{ status: 'failed', message: inj.message }];
            let n = 0;
            for (let i = 0; i < 15; i++) {
                await page.wait(1);
                n = await page.evaluate(`[...document.querySelector('[class*="_postForm_"]').querySelectorAll('img')].filter(i => i.src.startsWith('blob:')).length`);
                if (n >= imagePaths.length) break;
            }
            if (n < imagePaths.length) return [{ status: 'failed', message: `图片预览只出现 ${n}/${imagePaths.length} 张，未发送` }];
            await page.wait(5); // 给上传留时间
        }
        // 2. 在发帖框中输入文本
        const textResult = await page.evaluate(`(async () => {
      try {
        const textToInsert = ${JSON.stringify(kwargs.text)};

        // 首页发帖框在 _postForm_ 容器内，查找其中的 contenteditable
        const form = document.querySelector('[class*="_postForm_"]');
        const editor = form
          ? form.querySelector('[contenteditable="true"]')
          : document.querySelector('[contenteditable="true"]');

        if (editor) {
          editor.focus();
          // 用 ClipboardEvent paste 触发 React 状态更新
          const dt = new DataTransfer();
          dt.setData('text/plain', textToInsert);
          editor.dispatchEvent(new ClipboardEvent('paste', {
            clipboardData: dt, bubbles: true, cancelable: true,
          }));
          await new Promise(r => setTimeout(r, 800));

          // 检查是否成功插入
          const inserted = editor.textContent || '';
          if (inserted.length > 0) {
            return { ok: true, message: 'contenteditable' };
          }
        }

        // 回退：textarea
        const textarea = form
          ? form.querySelector('textarea')
          : document.querySelector('textarea');

        if (textarea) {
          textarea.focus();
          const setter = Object.getOwnPropertyDescriptor(
            HTMLTextAreaElement.prototype, 'value'
          )?.set;
          setter?.call(textarea, textToInsert);
          textarea.dispatchEvent(new Event('input', { bubbles: true }));
          await new Promise(r => setTimeout(r, 500));
          return { ok: true, message: 'textarea' };
        }

        return { ok: false, message: '未找到发帖输入框' };
      } catch (e) {
        return { ok: false, message: e.toString() };
      }
    })()`);
        if (!textResult.ok) {
            return [{ status: 'failed', message: textResult.message }];
        }
        if (kwargs['dry-run']) {
            const state = await page.evaluate(`(() => {
        const f = document.querySelector('[class*="_postForm_"]');
        return { chars: (f.querySelector('[contenteditable="true"]')?.textContent || '').length,
                 images: [...f.querySelectorAll('img')].filter(i => i.src.startsWith('blob:')).length };
      })()`);
            await page.evaluate('location.reload()');
            return [{ status: 'dry-run', message: `已填正文 ${state.chars} 字、图片 ${state.images} 张，未发送，发帖框已清空` }];
        }
        // 3. 点击"发送"按钮
        const submitResult = await page.evaluate(`(async () => {
      try {
        await new Promise(r => setTimeout(r, 500));

        // 即刻首页发帖框的按钮文字为"发送"
        const candidates = [
          ...Array.from(document.querySelectorAll('button')).filter(btn => {
            const text = btn.textContent?.trim() || '';
            return text === '发送' || text === '发布';
          }),
        ].filter(el => el && !el.disabled);

        if (candidates.length === 0) {
          return { ok: false, message: '未找到可用的发送按钮（按钮可能因内容为空而禁用）' };
        }

        candidates[0].click();
        return { ok: true, message: '动态发布成功' };
      } catch (e) {
        return { ok: false, message: e.toString() };
      }
    })()`);
        if (submitResult.ok) {
            await page.wait(3);
        }
        return [{
                status: submitResult.ok ? 'success' : 'failed',
                message: submitResult.message,
            }];
    },
});
