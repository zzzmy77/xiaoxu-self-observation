/* 日记模块 — 日历 + 富文本编辑 */
(function () {
    'use strict';

    var currentYear, currentMonth;

    // ── Calendar ──
    function renderCalendar(year, month) {
        currentYear = year;
        currentMonth = month;
        var grid = document.getElementById('calendarGrid');
        var title = document.getElementById('calTitle');
        if (!grid || !title) return;

        title.textContent = year + '年' + (month + 1) + '月';

        // Keep the header row
        while (grid.children.length > 7) {
            grid.removeChild(grid.lastChild);
        }

        var firstDay = new Date(year, month, 1).getDay();
        var daysInMonth = new Date(year, month + 1, 0).getDate();

        // Empty cells before first day
        for (var i = 0; i < firstDay; i++) {
            var empty = document.createElement('div');
            empty.className = 'cal-day cal-day-empty';
            grid.appendChild(empty);
        }

        // Day cells
        for (var d = 1; d <= daysInMonth; d++) {
            var cell = document.createElement('div');
            cell.className = 'cal-day';
            cell.dataset.date = year + '-' + pad(month + 1) + '-' + pad(d);
            cell.textContent = d;

            var today = new Date();
            if (year === today.getFullYear() && month === today.getMonth() && d === today.getDate()) {
                cell.classList.add('cal-day-today');
            }

            cell.addEventListener('click', function () {
                loadDayDetail(this.dataset.date);
            });

            grid.appendChild(cell);
        }

        // Load calendar data (mark days with entries)
        loadCalendarData(year, month + 1);
    }

    function loadCalendarData(year, month) {
        fetch('/diaries/api/calendar?year=' + year + '&month=' + month)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var cells = document.querySelectorAll('.cal-day[data-date]');
                cells.forEach(function (cell) {
                    var key = cell.dataset.date;
                    var info = data[key];
                    if (info) {
                        if (info.has_diary) cell.classList.add('cal-day-has-diary');
                        if (info.has_insight) cell.classList.add('cal-day-has-insight');
                        if (info.has_diary || info.has_insight) {
                            cell.classList.add('cal-day-has-data');
                            cell.title = (info.has_diary ? '📖 ' : '');
                        }
                    }
                });
            });
    }

    function pad(n) { return n < 10 ? '0' + n : '' + n; }

    // ── Day detail ──
    function loadDayDetail(dateStr) {
        var parts = dateStr.split('-');
        var detail = document.getElementById('dayDetail');
        var title = document.getElementById('dayDetailTitle');
        var diariesDiv = document.getElementById('dayDiaries');
        var insightsDiv = document.getElementById('dayInsights');
        if (!detail || !title || !diariesDiv || !insightsDiv) return;

        detail.style.display = 'block';
        title.textContent = dateStr;
        diariesDiv.innerHTML = '<p class="empty-state">加载中...</p>';
        insightsDiv.innerHTML = '';

        fetch('/diaries/api/day/' + parts[0] + '/' + parts[1] + '/' + parts[2])
            .then(function (r) { return r.json(); })
            .then(function (data) {
                diariesDiv.innerHTML = '';
                insightsDiv.innerHTML = '';

                if (data.diaries && data.diaries.length) {
                    diariesDiv.innerHTML = '<h4>📖 日记</h4>';
                    data.diaries.forEach(function (d) {
                        var card = document.createElement('div');
                        card.className = 'mini-card';
                        var contentPreview = (d.narrative || d.content || '').slice(0, 100);
                        if (!contentPreview) contentPreview = '暂无内容';
                        card.innerHTML = '<strong>' + (d.title || '无标题') + '</strong>'
                            + '<p>' + contentPreview + '...</p>'
                            + '<div class="mini-card-actions">'
                            + '<button class="btn-edit-diary" data-id="' + d.id + '">查看</button>'
                            + '<button class="btn-delete-diary" data-id="' + d.id + '">删除</button>'
                            + '</div>';
                        diariesDiv.appendChild(card);
                    });
                }
                if (data.insights && data.insights.length) {
                    insightsDiv.innerHTML = '<h4>🔍 洞察</h4>';
                    data.insights.forEach(function (i) {
                        var card = document.createElement('div');
                        card.className = 'mini-card';
                        var text = (i.insight_text || '').slice(0, 100) || '暂无摘要';
                        card.innerHTML = '<p>' + text + '...</p>';
                        insightsDiv.appendChild(card);
                    });
                }
                if (!data.diaries || !data.diaries.length) {
                    if (!data.insights || !data.insights.length) {
                        diariesDiv.innerHTML = '<p class="empty-state">这一天没有记录</p>';
                    }
                }
            })
            .catch(function () {
                diariesDiv.innerHTML = '<p class="empty-state">加载失败，请重试</p>';
            });
    }

    // Calendar nav
    var prevBtn = document.getElementById('calPrev');
    var nextBtn = document.getElementById('calNext');
    if (prevBtn && nextBtn) {
        prevBtn.addEventListener('click', function () {
            var m = currentMonth - 1;
            var y = currentYear;
            if (m < 0) { m = 11; y--; }
            renderCalendar(y, m);
        });
        nextBtn.addEventListener('click', function () {
            var m = currentMonth + 1;
            var y = currentYear;
            if (m > 11) { m = 0; y++; }
            renderCalendar(y, m);
        });
    }

    // ── Rich text editor ──
    var editingDiaryId = null;

    // Toolbar commands
    document.addEventListener('click', function (e) {
        var btn = e.target.closest('.editor-btn');
        if (!btn) return;

        var cmd = btn.dataset.cmd;
        var val = btn.dataset.val;
        document.execCommand(cmd, false, val || null);
        document.getElementById('editContent').focus();
    });

    // Open editor
    document.addEventListener('click', function (e) {
        var btn = e.target.closest('.btn-edit-diary');
        if (!btn) return;

        var id = btn.dataset.id;
        var modal = document.getElementById('diaryModal');
        if (!modal) return;

        modal.style.display = 'flex';
        editingDiaryId = id;

        fetch('/diaries/api/' + id)
            .then(function (r) { return r.json(); })
            .then(function (d) {
                document.getElementById('editTitle').value = d.title || '';
                document.getElementById('editTags').value = (d.emotion_tags || []).join(', ');
                document.getElementById('editContent').innerHTML = d.content || '';
            });
    });

    // Close modal
    function closeModal() {
        var modal = document.getElementById('diaryModal');
        if (modal) modal.style.display = 'none';
        editingDiaryId = null;
    }

    var closeBtn = document.getElementById('modalClose');
    var backdrop = document.getElementById('modalBackdrop');
    var cancelBtn = document.getElementById('editCancel');
    if (closeBtn) closeBtn.addEventListener('click', closeModal);
    if (backdrop) backdrop.addEventListener('click', closeModal);
    if (cancelBtn) cancelBtn.addEventListener('click', closeModal);

    // Save diary
    var saveBtn = document.getElementById('editSave');
    if (saveBtn) {
        saveBtn.addEventListener('click', function () {
            if (!editingDiaryId) return;

            var title = document.getElementById('editTitle').value;
            var tagsStr = document.getElementById('editTags').value;
            var content = document.getElementById('editContent').innerHTML;
            var tags = tagsStr.split(',').map(function (s) { return s.trim(); }).filter(Boolean);

            fetch('/diaries/api/' + editingDiaryId + '/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: title, content: content, emotion_tags: tags }),
            })
            .then(function (r) { return r.json(); })
            .then(function (d) {
                if (d.status === 'ok') {
                    closeModal();
                    location.reload();
                }
            });
        });
    }

    // ── Delete diary (list view) ──
    document.addEventListener('click', function (e) {
        var btn = e.target.closest('.btn-delete-diary');
        if (!btn) return;

        var id = btn.dataset.id;
        if (!confirm('确定要删除这篇日记吗？')) return;

        fetch('/diaries/api/' + id + '/delete', { method: 'POST' })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.status === 'ok') {
                    location.reload();
                } else {
                    alert(data.message || '删除失败');
                }
            });
    });

    // ── Delete diary (modal view) ──
    var modalDeleteBtn = document.getElementById('modalDelete');
    if (modalDeleteBtn) {
        modalDeleteBtn.addEventListener('click', function () {
            if (!editingDiaryId) return;

            if (!confirm('确定要删除这篇日记吗？删除后不可恢复。')) return;

            fetch('/diaries/api/' + editingDiaryId + '/delete', { method: 'POST' })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.status === 'ok') {
                        closeModal();
                        location.reload();
                    } else {
                        alert(data.message || '删除失败');
                    }
                });
        });
    }

    // ── Generate today's diary ──
    var genBtn = document.getElementById('btnGenerateToday');
    var regenBtn = document.getElementById('btnRegenerateToday');
    var genStatus = document.getElementById('generateStatus');

    function setGenerating(loading) {
        if (genBtn) genBtn.disabled = loading;
        if (regenBtn) regenBtn.disabled = loading;
        if (genStatus) {
            genStatus.textContent = loading ? '正在生成...' : '';
            genStatus.className = 'generate-status' + (loading ? ' generating' : '');
        }
    }

    function handleGenerate(force) {
        setGenerating(true);
        fetch('/diaries/api/generate-today', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ force: force || false }),
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            setGenerating(false);
            if (data.status === 'ok') {
                if (genStatus) {
                    genStatus.textContent = '✅ 日记已生成';
                    genStatus.className = 'generate-status success';
                }
                // Reload to show the new diary
                setTimeout(function () { location.reload(); }, 1000);
            } else if (data.status === 'exists') {
                if (genStatus) {
                    genStatus.textContent = '今天已有日记，点击「重新生成」覆盖';
                    genStatus.className = 'generate-status info';
                }
                if (genBtn) genBtn.style.display = 'none';
                if (regenBtn) regenBtn.style.display = 'inline-block';
            } else if (data.status === 'no_data') {
                if (genStatus) {
                    genStatus.textContent = data.message;
                    genStatus.className = 'generate-status warn';
                }
            } else {
                if (genStatus) {
                    genStatus.textContent = '❌ 生成失败：' + (data.message || '未知错误');
                    genStatus.className = 'generate-status error';
                }
            }
        })
        .catch(function (err) {
            setGenerating(false);
            if (genStatus) {
                genStatus.textContent = '❌ 网络错误，请重试';
                genStatus.className = 'generate-status error';
            }
        });
    }

    if (genBtn) {
        genBtn.addEventListener('click', function () {
            handleGenerate(false);
        });
    }
    if (regenBtn) {
        regenBtn.addEventListener('click', function () {
            if (!confirm('重新生成会覆盖当前日记，确定吗？')) return;
            handleGenerate(true);
        });
    }

    // Check if today already has a diary on page load
    (function checkTodayDiary() {
        var cards = document.querySelectorAll('.diary-card');
        var hasToday = false;
        cards.forEach(function (card) {
            var badge = card.querySelector('.today-badge');
            if (badge) hasToday = true;
        });
        if (hasToday) {
            if (genBtn) genBtn.style.display = 'none';
            if (regenBtn) regenBtn.style.display = 'inline-block';
            if (genStatus) {
                genStatus.textContent = '今天已有日记，可重新生成';
                genStatus.className = 'generate-status info';
            }
        }
    })();

    // ── Init ──
    var today = new Date();
    renderCalendar(today.getFullYear(), today.getMonth());
})();
