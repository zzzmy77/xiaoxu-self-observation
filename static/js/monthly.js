/* 月度总结（30天周期版） */
(function () {
    'use strict';

    var emotionChart = null;
    var attributionChart = null;
    var growthChart = null;
    var select = document.getElementById('periodSelect');
    var colors = ['#F9D8C6', '#A9C0D6', '#C6D8A0', '#E8B8A0', '#D4A0C8', '#A0C8C8', '#F0C8A0'];

    function populatePeriods() {
        fetch('/monthly/api/list')
            .then(function (r) { return r.json(); })
            .then(function (periods) {
                periods.forEach(function (p) {
                    var opt = document.createElement('option');
                    opt.value = p.period;
                    opt.textContent = p.label;
                    if (p.diary_count > 0) {
                        opt.textContent += ' (' + p.diary_count + '条)';
                    }
                    select.appendChild(opt);
                });
                // Select latest period with data, or the current one
                var latestWithData = null;
                periods.forEach(function (p) {
                    if (p.diary_count > 0) latestWithData = p;
                });
                if (latestWithData) {
                    select.value = latestWithData.period;
                } else if (periods.length) {
                    select.value = periods[periods.length - 1].period;
                }
                if (select.value) loadPeriod(select.value);
            });
    }

    function loadPeriod(period) {
        var card = document.getElementById('summaryCard');
        if (!card) return;
        card.innerHTML = '<div class="loading">加载周期总结...</div>';

        fetch('/monthly/api/' + period)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                renderSummary(data);
                renderCharts(data);
            });
    }

    function renderSummary(data) {
        var card = document.getElementById('summaryCard');
        if (!card) return;

        var timelineHtml = '';
        if (data.growth_timeline && data.growth_timeline.length) {
            timelineHtml = data.growth_timeline.map(function (t) {
                return '<div class="timeline-item"><span class="week-badge">第' + t.week + '周</span>'
                    + '<span>' + t.insight + '</span></div>';
            }).join('');
        }

        var discoveriesHtml = '';
        if (data.key_discoveries && data.key_discoveries.length) {
            discoveriesHtml = '<ul class="discovery-list">'
                + data.key_discoveries.map(function (d) { return '<li>' + d + '</li>'; }).join('')
                + '</ul>';
        }

        card.innerHTML = '<div class="summary-header"><h3>' + data.title + '</h3>'
            + '<span class="summary-subtitle">' + data.label + '</span></div>'
            + '<div class="summary-stats">'
            + '<span class="stat-chip">📖 ' + data.diary_count + ' 篇日记</span>'
            + '<span class="stat-chip">🔍 ' + data.insight_count + ' 条洞察</span>'
            + '</div>'
            + '<div class="summary-body">' + data.summary_text + '</div>'
            + (discoveriesHtml ? '<div class="summary-discoveries"><h4>关键发现</h4>' + discoveriesHtml + '</div>' : '')
            + (timelineHtml ? '<div class="summary-timeline"><h4>成长轨迹</h4>' + timelineHtml + '</div>' : '');
    }

    function renderCharts(data) {
        var emotions = data.emotion_frequencies || {};
        var attributions = data.attribution_distribution || {};
        var timeline = data.growth_timeline || [];

        // Emotion chart
        var ec = document.getElementById('emotionChart');
        if (ec) {
            if (emotionChart) emotionChart.destroy();
            var labels = Object.keys(emotions);
            var vals = Object.values(emotions);
            if (labels.length) {
                emotionChart = new Chart(ec, {
                    type: 'doughnut',
                    data: { labels: labels, datasets: [{ data: vals, backgroundColor: colors.slice(0, labels.length) }] },
                    options: { responsive: true, plugins: { legend: { position: 'right', labels: { font: { size: 11 } } } } }
                });
            } else {
                ec.parentElement.innerHTML = '<p class="empty-state">暂无数据</p>';
            }
        }

        // Attribution chart
        var ac = document.getElementById('attributionChart');
        if (ac) {
            if (attributionChart) attributionChart.destroy();
            var al = Object.keys(attributions);
            var av = Object.values(attributions);
            if (al.length) {
                var short = al.map(function (l) { return l.length > 15 ? l.slice(0, 15) + '..' : l; });
                attributionChart = new Chart(ac, {
                    type: 'bar',
                    data: { labels: short, datasets: [{ data: av, backgroundColor: colors.slice(0, al.length), borderRadius: 4 }] },
                    options: { responsive: true, indexAxis: 'y', plugins: { legend: { display: false } }, scales: { x: { ticks: { stepSize: 1 } }, y: { ticks: { font: { size: 10 } } } } }
                });
            } else {
                ac.parentElement.innerHTML = '<p class="empty-state">暂无数据</p>';
            }
        }

        // Growth chart
        var gc = document.getElementById('growthChart');
        if (gc && timeline.length) {
            if (growthChart) growthChart.destroy();
            var gl = timeline.map(function (t) { return '第' + t.week + '周'; });
            var gv = timeline.map(function (_, i) { return i + 1; });
            growthChart = new Chart(gc, {
                type: 'line',
                data: {
                    labels: gl,
                    datasets: [{ label: '成长进度', data: gv, borderColor: '#A9C0D6', backgroundColor: 'rgba(169,192,214,0.2)', fill: true, tension: 0.3, pointBackgroundColor: '#A9C0D6' }]
                },
                options: { responsive: true, plugins: { legend: { display: false }, tooltip: { callbacks: { label: function (ctx) { var t = timeline[ctx.dataIndex]; return t.insight ? t.insight.slice(0, 50) : ''; } } } }, scales: { y: { display: false } } }
            });
        } else if (gc) {
            gc.parentElement.innerHTML = '<p class="empty-state">继续记录，成长轨迹会在这里呈现</p>';
        }
    }

    if (select) {
        select.addEventListener('change', function () {
            if (this.value) loadPeriod(this.value);
        });
        populatePeriods();
    }
})();
