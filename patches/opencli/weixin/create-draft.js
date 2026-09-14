import { cli, Strategy } from '@jackwener/opencli/registry';
import { CommandExecutionError } from '@jackwener/opencli/errors';

const WEIXIN_DOMAIN = 'mp.weixin.qq.com';
const WEIXIN_HOME = 'https://mp.weixin.qq.com/';

async function getToken(page) {
    return page.evaluate(`(window.location.href.match(/token=(\\d+)/)||[])[1]`);
}

async function navigateToEditor(page) {
    await page.goto(WEIXIN_HOME);
    await page.wait(3);
    const token = await getToken(page);
    if (!token) {
        throw new CommandExecutionError('Could not extract session token. Please log in to mp.weixin.qq.com');
    }
    await page.goto(`https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit&isNew=1&type=77&token=${token}&lang=zh_CN`);
    await page.wait(4);
    const hasTitle = await page.evaluate('!!document.querySelector("textarea#title")');
    if (!hasTitle) {
        throw new CommandExecutionError('Article editor did not load. Session may have expired');
    }
}

async function fillField(page, selector, value) {
    return page.evaluate(`(() => {
        var el = document.querySelector('${selector}');
        if (!el) return { ok: false, reason: 'not found: ${selector}' };
        el.focus();
        var proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        var setter = Object.getOwnPropertyDescriptor(proto, 'value');
        if (setter && setter.set) setter.set.call(el, ${JSON.stringify(value)});
        else el.value = ${JSON.stringify(value)};
        el.dispatchEvent(new InputEvent('input', { bubbles: true, data: ${JSON.stringify(value)} }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.blur();
        return { ok: true };
    })()`);
}

async function fillContent(page, text) {
    return page.evaluate(`(() => {
        var editors = document.querySelectorAll('div[contenteditable="true"]');
        var editor = editors[editors.length - 1];
        if (!editor) return { ok: false, reason: 'content editor not found' };
        editor.focus();
        if (editor.querySelector('[contenteditable="false"]')) editor.innerHTML = '';
        document.execCommand('selectAll', false, null);
        document.execCommand('insertText', false, ${JSON.stringify(text)});
        editor.dispatchEvent(new InputEvent('input', { bubbles: true }));
        return { ok: true };
    })()`);
}

async function uploadContentImage(page, imagePath) {
    const fs = await import('node:fs');
    const path = await import('node:path');
    const absPath = path.default.resolve(imagePath);
    if (!fs.default.existsSync(absPath)) {
        throw new CommandExecutionError(`Image not found: ${absPath}`);
    }

    // 光标移到正文开头，图片插在顶部而不是末尾（2026-09-14）
    // 等 ProseMirror 把 insertText 的原始 DOM 规整成 span[leaf]，否则光标落空
    await page.wait(2);
    await page.evaluate(`(() => {
        var editors = document.querySelectorAll('div[contenteditable="true"]');
        var ed = editors[editors.length - 1];
        if (!ed) return;
        ed.focus();
        var leaf = ed.querySelector('span[leaf]');
        var r = document.createRange();
        r.setStart((leaf && leaf.firstChild) || ed, 0);
        r.collapse(true);
        var s = window.getSelection();
        s.removeAllRanges();
        s.addRange(r);
        document.dispatchEvent(new Event('selectionchange'));
    })()`);
    await page.wait(1.5);

    await page.evaluate(`(() => {
        var li = document.querySelector('#js_editor_insertimage');
        if (li) li.click();
    })()`);
    await page.wait(1);
    await page.evaluate(`(() => {
        var items = document.querySelectorAll('.js_img_dropdown_menu .tpl_dropdown_menu_item');
        if (items[0]) items[0].click();
    })()`);
    await page.wait(1);

    const buf = fs.default.readFileSync(absPath);
    const b64 = buf.toString('base64');
    const filename = path.default.basename(absPath);
    const mime = absPath.endsWith('.png') ? 'image/png' : 'image/jpeg';

    await page.evaluate(`(() => {
        const b = ${JSON.stringify(b64)};
        const bin = atob(b);
        const arr = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
        const file = new File([arr], ${JSON.stringify(filename)}, { type: ${JSON.stringify(mime)} });
        const inp = document.querySelector('input[type="file"][name="file"]');
        if (!inp) return 'no input';
        const dt = new DataTransfer();
        dt.items.add(file);
        inp.files = dt.files;
        inp.dispatchEvent(new Event('change', { bubbles: true }));
        return 'done';
    })()`);

    let cdnCount = 0;
    for (let i = 0; i < 15; i++) {
        await page.wait(2);
        cdnCount = await page.evaluate(`(() => {
            var editor = document.querySelector('#ueditor_0');
            return editor ? editor.querySelectorAll('img[src*="mmbiz"]').length : 0;
        })()`);
        if (cdnCount > 0) break;
    }
    if (cdnCount === 0) {
        throw new CommandExecutionError('Image did not upload to WeChat CDN');
    }
    const atTop = await page.evaluate(`(() => {
        var editors = document.querySelectorAll('div[contenteditable="true"]');
        var ed = editors[editors.length - 1];
        var img = ed && ed.querySelector('img[src*="mmbiz"]');
        var leaf = ed && ed.querySelector('span[leaf]');
        if (!img || !leaf || !leaf.textContent.trim()) return 'ok';
        if (img.compareDocumentPosition(leaf) & Node.DOCUMENT_POSITION_FOLLOWING) return 'ok';
        return ed.innerHTML.replace(/ (src|style|data-[a-z-]+|class|alt)="[^"]*"/g, '').slice(0, 300);
    })()`);
    if (atTop !== 'ok') {
        throw new CommandExecutionError('配图没插到正文顶部：' + atTop);
    }
}

async function selectCoverFromContent(page) {
    await page.evaluate('document.querySelector("#js_cover_description_area")?.scrollIntoView()');
    await page.wait(1);

    await page.evaluate('document.querySelector(".js_cover_btn_area")?.click()');
    await page.wait(1);

    await page.evaluate(`(() => {
        var links = document.querySelectorAll('a.pop-opr__button');
        for (var i = 0; i < links.length; i++) {
            if (links[i].textContent.trim() === '从正文选择') { links[i].click(); return; }
        }
    })()`);
    await page.wait(2);

    await page.evaluate(`(() => {
        var img = document.querySelector('.weui-desktop-dialog_img-picker .appmsg_content_img');
        if (img) img.click();
    })()`);
    await page.wait(1);

    await page.evaluate(`(() => {
        var btns = document.querySelectorAll('.weui-desktop-dialog_img-picker button');
        for (var i = 0; i < btns.length; i++) {
            if (btns[i].textContent.trim() === '下一步' && !btns[i].disabled) { btns[i].click(); return; }
        }
    })()`);

    // Crop dialog image rendering can be slow
    for (let attempt = 0; attempt < 8; attempt++) {
        await page.wait(2);
        const ready = await page.evaluate(`(() => {
            var btns = document.querySelectorAll('button');
            for (var i = 0; i < btns.length; i++) {
                if (btns[i].textContent.trim() === '确认' && btns[i].offsetHeight > 0 && !btns[i].disabled) return true;
            }
            return false;
        })()`);
        if (ready) break;
    }

    await page.evaluate(`(() => {
        var btns = document.querySelectorAll('button');
        for (var i = 0; i < btns.length; i++) {
            if (btns[i].textContent.trim() === '确认' && btns[i].offsetHeight > 0 && !btns[i].disabled) { btns[i].click(); return; }
        }
    })()`);
    await page.wait(2);
    const hasCover = await page.evaluate(`(() => {
        var area = document.querySelector('#js_cover_area');
        if (!area) return false;
        var found = false;
        area.querySelectorAll('*').forEach(function(el) {
            var bg = window.getComputedStyle(el).backgroundImage;
            if (bg && bg.includes('mmbiz')) found = true;
        });
        return found;
    })()`);
    return hasCover;
}

async function clickSaveDraft(page) {
    const result = await page.evaluate(`(() => {
        var btns = document.querySelectorAll('span, button, a');
        for (var i = 0; i < btns.length; i++) {
            if ((btns[i].textContent || '').trim() === '保存为草稿') { btns[i].click(); return { ok: true }; }
        }
        return { ok: false };
    })()`);
    if (!result?.ok) throw new CommandExecutionError('Save draft button not found');

    for (let attempt = 0; attempt < 5; attempt++) {
        await page.wait(2);
        const saved = await page.evaluate(`(() => {
            var el = document.querySelector('#js_save_success');
            if (el && window.getComputedStyle(el).display !== 'none') return true;
            return document.body.innerText.includes('已保存');
        })()`);
        if (saved) return true;
    }
    return false;
}

export const createDraftCommand = cli({
    site: 'weixin',
    name: 'create-draft',
    access: 'write',
    description: '创建微信公众号图文草稿',
    domain: WEIXIN_DOMAIN,
    strategy: Strategy.COOKIE,
    browser: true,
    navigateBefore: false,
    args: [
        { name: 'title', required: true, help: '文章标题 (最长64字)' },
        { name: 'content', required: true, positional: true, help: '文章正文' },
        { name: 'author', help: '作者名 (最长8字)' },
        { name: 'cover-image', help: '封面图片路径 (会先上传到正文再设为封面)' },
        { name: 'summary', help: '文章摘要' },
        { name: 'timeout', type: 'int', required: false, default: 180, help: 'Max seconds for the overall command (default: 180)' },
    ],
    columns: ['status', 'detail'],

    func: async (page, kwargs) => {
        await navigateToEditor(page);

        const titleResult = await fillField(page, 'textarea#title', kwargs.title);
        if (!titleResult?.ok) throw new CommandExecutionError('Failed to fill title');

        if (kwargs.author) {
            const authorResult = await fillField(page, 'input#author', kwargs.author);
            if (!authorResult?.ok) throw new CommandExecutionError('Failed to fill author');
        }

        const contentResult = await fillContent(page, kwargs.content);
        if (!contentResult?.ok) throw new CommandExecutionError('Failed to fill content');

        if (kwargs['cover-image']) {
            await uploadContentImage(page, kwargs['cover-image']);
            const coverSet = await selectCoverFromContent(page);
            if (!coverSet) {
                // Non-fatal: draft can be saved without cover
            }
        }

        if (kwargs.summary) {
            await fillField(page, 'textarea#js_description', kwargs.summary);
        }

        await page.wait(1);
        const success = await clickSaveDraft(page);

        return [{
            status: success ? 'draft saved' : 'save attempted, check browser to confirm',
            detail: `"${kwargs.title}"${kwargs.author ? ` by ${kwargs.author}` : ''}${kwargs['cover-image'] ? ' (with cover)' : ''}`,
        }];
    },
});
