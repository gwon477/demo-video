// Camino sample app - static, no build step. Serves as the regression target
// for the demo-video skill: every interaction kind in references/interactions.md
// exists here in its simplest form.
(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  // Header nav current page
  const here = location.pathname.split('/').pop() || 'index.html';
  $$('header nav a').forEach((a) => {
    if (a.getAttribute('href') === here) a.setAttribute('aria-current', 'page');
  });

  // Command palette (⌘K / Ctrl+K)
  const palette = $('#palette');
  if (palette) {
    document.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        palette.toggleAttribute('open');
        if (palette.hasAttribute('open')) $('#palette input').focus();
      }
      if (e.key === 'Escape') palette.removeAttribute('open');
    });
    palette.addEventListener('click', (e) => { if (e.target === palette) palette.removeAttribute('open'); });
  }

  // Dashboard: fail rows open the detail panel
  $$('tr[data-testid^="fail-row"]').forEach((tr) => {
    tr.addEventListener('click', () => {
      const detail = $('[data-testid=fail-detail]');
      detail.hidden = false;
      $('[data-testid=fail-detail-name]').textContent = tr.dataset.name;
      $('[data-testid=fail-detail-msg]').textContent = tr.dataset.msg;
    });
  });

  // Pointer-based sortable list (dnd-kit / SortableJS style: pointerdown, pointermove, pointerup)
  const plist = $('[data-testid=pointer-list]');
  if (plist) {
    let dragging = null;
    plist.addEventListener('pointerdown', (e) => {
      const li = e.target.closest('li');
      if (!li || !e.target.closest('.handle')) return;
      dragging = li;
      li.classList.add('dragging');
      li.setPointerCapture(e.pointerId);
    });
    plist.addEventListener('pointermove', (e) => {
      if (!dragging) return;
      const over = document.elementFromPoint(e.clientX, e.clientY)?.closest('li');
      $$('li', plist).forEach((l) => l.classList.toggle('over', l === over && l !== dragging));
      if (over && over !== dragging) {
        const rect = over.getBoundingClientRect();
        const before = e.clientY < rect.top + rect.height / 2;
        plist.insertBefore(dragging, before ? over : over.nextSibling);
      }
    });
    const end = () => {
      if (!dragging) return;
      dragging.classList.remove('dragging');
      $$('li', plist).forEach((l) => l.classList.remove('over'));
      dragging = null;
      $('[data-testid=pointer-order]').textContent = $$('li', plist).map((l) => l.dataset.id).join(' > ');
    };
    plist.addEventListener('pointerup', end);
    plist.addEventListener('pointercancel', end);
  }

  // Native HTML5 draggable list (dragstart / dragover / drop)
  const hlist = $('[data-testid=html5-list]');
  if (hlist) {
    let src = null;
    hlist.addEventListener('dragstart', (e) => {
      src = e.target.closest('li');
      src.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', src.dataset.id);
    });
    hlist.addEventListener('dragover', (e) => {
      e.preventDefault();
      const over = e.target.closest('li');
      $$('li', hlist).forEach((l) => l.classList.toggle('over', l === over && l !== src));
    });
    hlist.addEventListener('drop', (e) => {
      e.preventDefault();
      const over = e.target.closest('li');
      if (over && src && over !== src) {
        const rect = over.getBoundingClientRect();
        hlist.insertBefore(src, e.clientY < rect.top + rect.height / 2 ? over : over.nextSibling);
      }
      $('[data-testid=html5-order]').textContent = $$('li', hlist).map((l) => l.dataset.id).join(' > ');
    });
    hlist.addEventListener('dragend', () => {
      $$('li', hlist).forEach((l) => l.classList.remove('dragging', 'over'));
      src = null;
    });
  }

  // File dropzone
  const dz = $('[data-testid=dropzone]');
  if (dz) {
    const input = $('input[type=file]', dz);
    const show = (files) => {
      const ul = $('[data-testid=file-list]');
      ul.innerHTML = '';
      [...files].forEach((f) => {
        const li = document.createElement('li');
        li.textContent = `${f.name} (${f.size} bytes)`;
        ul.appendChild(li);
      });
      $('[data-testid=upload-status]').textContent = `${files.length}개 파일 업로드 완료`;
    };
    ['dragenter', 'dragover'].forEach((t) => dz.addEventListener(t, (e) => { e.preventDefault(); dz.classList.add('over'); }));
    ['dragleave', 'drop'].forEach((t) => dz.addEventListener(t, (e) => { e.preventDefault(); dz.classList.remove('over'); }));
    dz.addEventListener('drop', (e) => show(e.dataTransfer.files));
    input.addEventListener('change', () => show(input.files));
    dz.addEventListener('click', (e) => { if (e.target === dz || e.target.tagName === 'P') input.click(); });
  }

  // Streaming response
  const send = $('[data-testid=chat-send]');
  if (send) {
    const answer = '요청하신 실패 테스트 3건을 분석했습니다.\n\n1. login-flow: 로그인 버튼의 셀렉터가 변경되었습니다. data-testid=submit 으로 갱신하면 통과합니다.\n2. checkout-total: 합계 계산에서 배송비가 두 번 더해집니다. 서버 응답의 shipping 필드를 확인하세요.\n3. export-csv: 파일 이름의 날짜 형식이 로케일에 따라 달라집니다. ISO 형식으로 고정하는 것을 권장합니다.\n\n세 건 모두 재현 스텝을 각 케이스에 첨부했습니다.';
    send.addEventListener('click', () => {
      const q = $('[data-testid=chat-input]').value.trim() || '실패한 테스트를 분석해줘';
      const chat = $('[data-testid=chat-log]');
      const u = document.createElement('div'); u.className = 'msg user'; u.textContent = q; chat.appendChild(u);
      const b = document.createElement('div'); b.className = 'msg bot'; b.setAttribute('data-testid', 'chat-answer'); chat.appendChild(b);
      const st = $('[data-testid=chat-status]');
      st.dataset.state = 'streaming'; st.textContent = '분석 중...';
      let i = 0;
      const t = setInterval(() => {
        b.textContent = answer.slice(0, i += 3);
        if (i >= answer.length) { clearInterval(t); st.dataset.state = 'done'; st.textContent = '완료'; }
      }, 40);
    });
  }

  // Context menu, double-click inline edit, resizable split, slider
  const menu = $('#ctx-menu');
  if (menu) {
    document.addEventListener('contextmenu', (e) => {
      const row = e.target.closest('[data-ctx]');
      if (!row) return;
      e.preventDefault();
      menu.style.left = e.clientX + 'px'; menu.style.top = e.clientY + 'px';
      menu.setAttribute('open', '');
      menu.dataset.target = row.dataset.ctx;
    });
    document.addEventListener('click', () => menu.removeAttribute('open'));
    $$('#ctx-menu div').forEach((d) => d.addEventListener('click', () => {
      $('[data-testid=ctx-result]').textContent = `${menu.dataset.target}: ${d.textContent}`;
    }));
  }
  $$('.editable').forEach((el) => {
    el.addEventListener('dblclick', () => {
      const input = document.createElement('input');
      input.type = 'text'; input.value = el.textContent; input.setAttribute('aria-label', '이름 편집');
      el.replaceChildren(input); input.focus(); input.select();
      const commit = () => { el.textContent = input.value; };
      input.addEventListener('blur', commit);
      input.addEventListener('keydown', (e) => { if (e.key === 'Enter') input.blur(); });
    });
  });
  const sep = $('.split .sep');
  if (sep) {
    const left = $('.split .pane');
    let on = false;
    sep.addEventListener('pointerdown', (e) => { on = true; sep.setPointerCapture(e.pointerId); });
    sep.addEventListener('pointermove', (e) => { if (on) left.style.width = Math.max(120, e.clientX - left.getBoundingClientRect().left) + 'px'; });
    sep.addEventListener('pointerup', () => { on = false; });
  }
  const range = $('input[type=range]');
  if (range) {
    const out = $('[data-testid=range-out]');
    const upd = () => { out.textContent = `${range.value}% 임계값`; };
    range.addEventListener('input', upd); upd();
  }
})();
