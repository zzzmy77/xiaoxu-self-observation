/* 洞察 V2 — 情绪云气泡图 + 认知模式卡片 + 转变支点 */
(function () {
    'use strict';

    var EMOTION_NAMES = {
        '焦虑': '😰', '压力': '😣', '委屈': '🥺', '愤怒': '😠',
        '沮丧': '😞', '无力': '😩', '失落': '😿', '不安': '😥',
        '悲伤': '😢', '自我怀疑': '🤨', '烦躁': '😤', '恐惧': '😨',
        '困惑': '🤔', '开心': '😊', '放松': '😌', '觉察': '💡',
        '思考': '🧐', '自豪': '🎉',
    };

    // ── 主入口 ──
    function loadV2() {
        var container = document.querySelector('.insights-container');
        if (!container) return;

        // Show loading
        var main = document.getElementById('insightsMain');
        if (!main) {
            main = document.createElement('div');
            main.id = 'insightsMain';
            container.insertBefore(main, container.querySelector('.insight-list'));
        }
        main.innerHTML = '<div class="v2-loading">加载中...</div>';

        fetch('/insights/api/v2')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                renderV2(main, data);
            })
            .catch(function (err) {
                main.innerHTML = '<div class="v2-loading error">加载失败，请刷新重试</div>';
            });
    }

    // ── 渲染引擎 ──
    function renderV2(container, data) {
        var html = '';

        // 1. Mood headline
        html += '<div class="v2-headline">'
            + '<div class="v2-headline-icon">☀️</div>'
            + '<div class="v2-headline-text">' + escapeHtml(data.mood_headline) + '</div>'
            + '</div>';

        // 2. Emotion cloud
        html += '<div class="v2-card v2-card-emotion">'
            + '<h4>😊 近期情绪状态</h4>'
            + '<div class="emotion-cloud-wrap">'
            + '<canvas id="emotionCloudCanvas" width="360" height="200"></canvas>'
            + '</div>';
        if (data.warm_message) {
            html += '<div class="v2-warm-msg">💬 ' + escapeHtml(data.warm_message) + '</div>';
        }
        html += '</div>';

        // 3. Key discoveries (时间线)
        if (data.key_discoveries && data.key_discoveries.length) {
            html += '<div class="v2-card v2-card-insights">'
                + '<h4>🔍 这几次聊天的发现</h4>'
                + '<div class="v2-timeline">';
            data.key_discoveries.forEach(function (d) {
                var emotions = (d.emotions || []).map(function (e) {
                    return '<span class="tag">' + e + '</span>';
                }).join('');
                html += '<div class="v2-timeline-item">'
                    + '<div class="v2-tl-date">' + escapeHtml(d.date) + '</div>'
                    + '<div class="v2-tl-content">'
                    + '<div class="v2-tl-title">' + escapeHtml(d.title) + '</div>'
                    + emotions
                    + '</div></div>';
            });
            html += '</div></div>';
        }

        // 4. Cognitive patterns
        if (data.cognitive_patterns && data.cognitive_patterns.length) {
            html += '<div class="v2-card v2-card-patterns">'
                + '<h4>🧠 你的认知模式</h4>'
                + '<div class="v2-pattern-list">';
            data.cognitive_patterns.forEach(function (p) {
                var count = p.occurrence_count || 0;
                var firstSeen = p.first_seen ? '· 最早 ' + p.first_seen : '';
                var evolution = (p.evolution || []).map(function (s) {
                    return '<span class="v2-evo-dot">' + s + '</span>';
                }).join(' → ');
                html += '<div class="v2-pattern-card">'
                    + '<div class="v2-pattern-name">' + escapeHtml(p.name) + '</div>'
                    + '<div class="v2-pattern-meta">出现 ' + count + ' 次 ' + firstSeen + '</div>';
                if (p.behavior || p.cognition) {
                    html += '<div class="v2-pattern-detail">';
                    if (p.behavior) {
                        html += '<div class="v2-pd-row"><span class="v2-pd-label">行为</span>'
                            + escapeHtml(p.behavior) + '</div>';
                    }
                    if (p.cognition) {
                        html += '<div class="v2-pd-row"><span class="v2-pd-label">认知</span>'
                            + escapeHtml(p.cognition) + '</div>';
                    }
                    html += '</div>';
                }
                if (evolution) {
                    html += '<div class="v2-pattern-evolution">' + evolution + '</div>';
                }
                if (p.triggers && p.triggers.length) {
                    html += '<div class="v2-pattern-triggers">触发：'
                        + p.triggers.map(function (t) { return '<span class="tag">' + escapeHtml(t) + '</span>'; }).join('')
                        + '</div>';
                }
                html += '</div>';
            });
            html += '</div></div>';
        }

        // 5. Pivot point
        if (data.pivot_point) {
            html += '<div class="v2-card v2-card-pivot">'
                + '<h4>🌱 一个转变的支点</h4>'
                + '<div class="v2-pivot-text">' + escapeHtml(data.pivot_point) + '</div>'
                + '</div>';
        }



        container.innerHTML = html;

        // ── 气泡图 ──
        drawBubbleChart(data.emotion_cloud);

        // ── 日历初始化 ──
        initInsightCalendar();
    }

    // ── 气泡图（纯 Canvas）──
    function drawBubbleChart(cloudData) {
        var canvas = document.getElementById('emotionCloudCanvas');
        if (!canvas) return;

        var bubbles = (cloudData && cloudData.bubbles) || [];
        if (!bubbles.length) {
            var ctx = canvas.getContext('2d');
            ctx.fillStyle = '#ccc';
            ctx.font = '14px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('暂无数据', canvas.width / 2, canvas.height / 2);
            return;
        }

        var ctx = canvas.getContext('2d');
        var w = canvas.width;
        var h = canvas.height;

        ctx.clearRect(0, 0, w, h);

        // 分两组：negative 偏左，positive 偏右
        var negBubbles = bubbles.filter(function (b) { return b.group === 'negative'; });
        var posBubbles = bubbles.filter(function (b) { return b.group !== 'negative'; });

        // 计算布局：negative 在左半区，positive 在右半区
        var centerX = w / 2;
        var centerY = h / 2;
        var maxR = 45;

        // 在左右半区均匀分布
        function layoutBubbles(bubbleList, xCenter, xSpread) {
            var total = bubbleList.length;
            if (total === 0) return;
            var cols = Math.ceil(Math.sqrt(total));
            var rows = Math.ceil(total / cols);
            var spacingX = xSpread / Math.max(cols, 1);
            var spacingY = (h - 40) / Math.max(rows, 1);

            bubbleList.forEach(function (b, i) {
                var col = i % cols;
                var row = Math.floor(i / cols);
                var r = Math.max(15, b.size * maxR);
                var x = xCenter - xSpread / 2 + spacingX * col + spacingX / 2;
                var y = 20 + spacingY * row + spacingY / 2;

                // 绘制气泡
                ctx.beginPath();
                ctx.arc(x, y, r, 0, Math.PI * 2);
                ctx.fillStyle = b.color + '60'; // 半透明
                ctx.fill();
                ctx.strokeStyle = b.color;
                ctx.lineWidth = 1.5;
                ctx.stroke();

                // 情绪名
                ctx.fillStyle = '#333';
                ctx.font = Math.max(10, r * 0.5) + 'px sans-serif';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(b.emotion, x, y - 6);

                // emoji
                var emoji = EMOTION_NAMES[b.emotion] || '';
                if (emoji) {
                    ctx.font = Math.max(12, r * 0.45) + 'px sans-serif';
                    ctx.textBaseline = 'bottom';
                    ctx.fillText(emoji, x, y + r + 6);
                }
            });
        }

        layoutBubbles(negBubbles, w * 0.3, w * 0.45);
        layoutBubbles(posBubbles, w * 0.7, w * 0.45);

        // 分隔标签
        ctx.fillStyle = '#999';
        ctx.font = '11px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillText('负面', w * 0.2, h - 16);
        ctx.fillText('正面', w * 0.8, h - 16);

        // 中间的柔和分隔线
        ctx.beginPath();
        ctx.strokeStyle = '#e0e0e0';
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 4]);
        ctx.moveTo(w / 2, 10);
        ctx.lineTo(w / 2, h - 20);
        ctx.stroke();
        ctx.setLineDash([]);
    }

    // ── 日历 ──
    var _calYear, _calMonth;

    function initInsightCalendar() {
        var today = new Date();
        renderInsightCal(today.getFullYear(), today.getMonth());
    }

    function renderInsightCal(year, month) {
        _calYear = year;
        _calMonth = month;
        var grid = document.getElementById('insightCalGrid');
        var title = document.getElementById('insightCalTitle');
        if (!grid || !title) return;

        title.textContent = year + '年' + (month + 1) + '月';

        while (grid.children.length > 7) {
            grid.removeChild(grid.lastChild);
        }

        var firstDay = new Date(year, month, 1).getDay();
        var daysInMonth = new Date(year, month + 1, 0).getDate();

        for (var i = 0; i < firstDay; i++) {
            var empty = document.createElement('div');
            empty.className = 'cal-day cal-day-empty';
            grid.appendChild(empty);
        }

        for (var d = 1; d <= daysInMonth; d++) {
            var cell = document.createElement('div');
            cell.className = 'cal-day';
            cell.dataset.date = year + '-' + _pad(month + 1) + '-' + _pad(d);
            cell.textContent = d;

            var today = new Date();
            if (year === today.getFullYear() && month === today.getMonth() && d === today.getDate()) {
                cell.classList.add('cal-day-today');
            }

            cell.addEventListener('click', function () {
                filterByDate(this.dataset.date);
            });

            grid.appendChild(cell);
        }

        loadInsightCalData(year, month + 1);
    }

    function loadInsightCalData(year, month) {
        fetch('/insights/api/calendar?year=' + year + '&month=' + month)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var cells = document.querySelectorAll('#insightCalGrid .cal-day[data-date]');
                cells.forEach(function (cell) {
                    if (data[cell.dataset.date]) {
                        cell.classList.add('cal-day-has-data', 'cal-day-has-insight');
                    }
                });
            });
    }

    function filterByDate(dateStr) {
        // Clear previous selection
        document.querySelectorAll('#insightCalGrid .cal-day-selected').forEach(function (c) {
            c.classList.remove('cal-day-selected');
        });

        // Mark selected day
        var cells = document.querySelectorAll('#insightCalGrid .cal-day[data-date]');
        cells.forEach(function (c) {
            if (c.dataset.date === dateStr) {
                c.classList.add('cal-day-selected');
            }
        });

        // Show banner
        var banner = document.getElementById('insightDateFilterBanner');
        var label = document.getElementById('insightDateLabel');
        if (banner && label) {
            var parts = dateStr.split('-');
            label.textContent = '📅 ' + parts[0] + '年' + parseInt(parts[1]) + '月' + parseInt(parts[2]) + '日的洞察';
            banner.style.display = 'flex';
        }

        // Filter insight cards
        var cards = document.querySelectorAll('.insight-card');
        var hasMatch = false;
        cards.forEach(function (card) {
            if (card.dataset.date === dateStr) {
                card.style.display = 'block';
                hasMatch = true;
            } else {
                card.style.display = 'none';
            }
        });

        // Show empty state if no matches
        var empty = document.querySelector('.insight-list .empty-state-guide');
        if (!empty) {
            var list = document.querySelector('.insight-list');
            if (list && !list.querySelector('.empty-state-guide')) {
                var el = document.createElement('div');
                el.className = 'empty-state-guide insight-date-empty';
                el.innerHTML = '<h3>这一天没有洞察</h3>';
                el.style.display = hasMatch ? 'none' : 'block';
                list.appendChild(el);
            }
        }
        var dateEmpty = document.querySelector('.insight-date-empty');
        if (dateEmpty) {
            dateEmpty.style.display = hasMatch ? 'none' : 'block';
        }
    }

    function clearDateFilter() {
        // Clear selection
        document.querySelectorAll('#insightCalGrid .cal-day-selected').forEach(function (c) {
            c.classList.remove('cal-day-selected');
        });

        // Hide banner
        var banner = document.getElementById('insightDateFilterBanner');
        if (banner) banner.style.display = 'none';

        // Show all cards
        document.querySelectorAll('.insight-card').forEach(function (card) {
            card.style.display = 'block';
        });

        // Hide date-empty notice
        var dateEmpty = document.querySelector('.insight-date-empty');
        if (dateEmpty) dateEmpty.style.display = 'none';
    }

    // Clear filter button
    document.addEventListener('click', function (e) {
        if (e.target.closest('#insightDateClear')) {
            clearDateFilter();
        }
    });

    // Calendar nav
    document.addEventListener('click', function (e) {
        var prev = e.target.closest('#insightCalPrev');
        var next = e.target.closest('#insightCalNext');
        if (prev) {
            var m = _calMonth - 1, y = _calYear;
            if (m < 0) { m = 11; y--; }
            renderInsightCal(y, m);
        }
        if (next) {
            var m = _calMonth + 1, y = _calYear;
            if (m > 11) { m = 0; y++; }
            renderInsightCal(y, m);
        }
    });

    function _pad(n) { return n < 10 ? '0' + n : '' + n; }

    // ── Helper ──
    function escapeHtml(str) {
        if (!str) return '';
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(str));
        return div.innerHTML;
    }

    // ── 等页面加载完再执行 ──
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', loadV2);
    } else {
        loadV2();
    }
})();
