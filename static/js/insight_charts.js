/* 洞察页图表 */
(function () {
    'use strict';

    var emotionChart = null;
    var colors = ['#F9D8C6', '#A9C0D6', '#C6D8A0', '#E8B8A0', '#D4A0C8', '#A0C8C8', '#F0C8A0'];

    // Dashboard
    function loadDashboard() {
        var dash = document.getElementById('dashboard');
        if (!dash) return;

        Promise.all([
            fetch('/insights/api/data').then(function (r) { return r.json(); }),
            fetch('/insights/').then(function () { return; }), // ensure data loaded
        ])
        .then(function (results) {
            var data = results[0];
            var emotions = data.emotion_frequencies || {};
            var attributions = data.attributions || [];
            var insights = data.self_insights || [];

            var emKeys = Object.keys(emotions);
            var emTotal = data.total_emotions || 0;
            var topEm = emKeys.length ? emKeys.slice(0, 3).join(', ') : '暂无数据';

            var topAttr = attributions.length ? attributions[0].text.slice(0, 40) : '暂无数据';

            var lastInsight = insights.length ? insights[insights.length - 1].text.slice(0, 80) : '暂无数据';

            // Build patterns section (legacy keyword-based)
            var patternsHtml = '';
            if (data.patterns && data.patterns.length) {
                patternsHtml = '<div class="dash-section insight-timeline" style="grid-column:1/-1">'
                    + '<h4>🌟 模式发现</h4>'
                    + data.patterns.map(function(p) {
                        return '<div class="insight-timeline-item">' + p + '</div>';
                    }).join('')
                    + '</div>';
            }

            // ── Core Beliefs Section ──
            var beliefsHtml = '';
            if (data.core_beliefs && data.core_beliefs.length) {
                beliefsHtml = '<div class="dash-section" style="grid-column:1/-1">'
                    + '<h4>🧠 核心信念</h4><div class="belief-list">';
                data.core_beliefs.forEach(function(b) {
                    var formed = b.formed_at ? ('<span class="belief-date">' + b.formed_at + '</span>') : '';
                    var confidence = b.confidence ? Math.round(b.confidence * 100) + '%' : '';
                    beliefsHtml += '<div class="belief-card">'
                        + '<p class="belief-text">' + escapeHtml(b.belief) + '</p>'
                        + '<div class="belief-meta">' + formed + ' ' + confidence + '</div>'
                        + '</div>';
                });
                beliefsHtml += '</div></div>';
            }

            // ── Cognitive Pattern Library Section ──
            var patternLibHtml = '';
            if (data.pattern_library && data.pattern_library.length) {
                patternLibHtml = '<div class="dash-section insight-timeline" style="grid-column:1/-1">'
                    + '<h4>📚 认知模式库</h4>'
                    + data.pattern_library.map(function(p) {
                        var count = p.occurrence_count || 1;
                        var timeline = '';
                        if (p.first_seen) {
                            timeline = '首次: ' + p.first_seen;
                            if (p.last_seen && p.last_seen !== p.first_seen) {
                                timeline += ' → 最近: ' + p.last_seen;
                            }
                        }
                        return '<div class="insight-timeline-item">'
                            + '<div class="pattern-text">' + escapeHtml(p.pattern) + '</div>'
                            + '<div class="pattern-meta">出现 ' + count + ' 次' + (timeline ? ' · ' + timeline : '') + '</div>'
                            + '</div>';
                    }).join('')
                    + '</div>';
            }

            // ── Relationship Dynamics Section ──
            var relHtml = '';
            if (data.relationships && data.relationships.length) {
                relHtml = '<div class="dash-section" style="grid-column:1/-1">'
                    + '<h4>👥 核心关系网络</h4><div class="relationship-list">'
                    + data.relationships.map(function(r) {
                        var impact = r.impact ? '<br><span class="rel-impact">' + escapeHtml(r.impact) + '</span>' : '';
                        return '<div class="relationship-card">'
                            + '<strong>' + escapeHtml(r.name || '') + '</strong>'
                            + (r.role ? ' · ' + escapeHtml(r.role) : '')
                            + impact
                            + '</div>';
                    }).join('')
                    + '</div></div>';
            }

            // ── Traits Section ──
            var traitsHtml = '';
            if (data.traits && (data.traits.behavioral || data.traits.cognitive)) {
                traitsHtml = '<div class="dash-section" style="grid-column:1/-1">'
                    + '<h4>🎭 人格与认知特征</h4><div class="traits-list">';
                if (data.traits.behavioral && data.traits.behavioral.length) {
                    traitsHtml += '<div class="trait-group"><h5>行为特征</h5><ul>'
                        + data.traits.behavioral.map(function(t) { return '<li>' + escapeHtml(t) + '</li>'; }).join('')
                        + '</ul></div>';
                }
                if (data.traits.cognitive && data.traits.cognitive.length) {
                    traitsHtml += '<div class="trait-group"><h5>认知特征</h5><ul>'
                        + data.traits.cognitive.map(function(t) { return '<li>' + escapeHtml(t) + '</li>'; }).join('')
                        + '</ul></div>';
                }
                traitsHtml += '</div></div>';
            }

            dash.innerHTML = '<div class="dashboard-grid">'
                + '<div class="dash-section"><h4>😊 高频情绪</h4><p class="dash-value">' + topEm + '</p></div>'
                + '<div class="dash-section"><h4>🎯 最常见归因</h4><p class="dash-value">' + topAttr + '</p></div>'
                + '<div class="dash-section"><h4>📊 总情绪标记</h4><p class="dash-value">' + emTotal + ' 次</p></div>'
                + '<div class="dash-section"><h4>📝 最新洞察</h4><p class="dash-value">' + lastInsight + '</p></div>'
                + patternsHtml
                + beliefsHtml
                + patternLibHtml
                + relHtml
                + traitsHtml
                + '</div>';

            // Render emotion chart
            renderEmotionChart(emotions);
        });
    }

    // ── Helpers ──
    function escapeHtml(str) {
        if (!str) return '';
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(str));
        return div.innerHTML;
    }

    function renderEmotionChart(emotions) {
        var canvas = document.getElementById('insightEmotionChart');
        if (!canvas) return;
        if (emotionChart) emotionChart.destroy();

        var labels = Object.keys(emotions);
        var values = Object.values(emotions);

        if (!labels.length) {
            canvas.parentElement.innerHTML = '<p class="empty-state">暂无情绪分布数据。🧪 试试侧边栏的测试工具，或者多和小绪聊几次</p>';
            return;
        }

        emotionChart = new Chart(canvas, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{ data: values, backgroundColor: colors.slice(0, labels.length) }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { position: 'right', labels: { font: { size: 11 } } }
                }
            }
        });
    }

    loadDashboard();
})();
