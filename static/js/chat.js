/* 小绪 · 前端交互 - 沉浸式对话版 */
(function () {
    'use strict';

    // ── 归因文本质量过滤 ──
    function isValidAttribution(text) {
        if (!text || text.length < 3) return false;
        var generic = ['用户','外部','内部','自己','别人','他人','环境','社会','家庭','工作','学习','生活','性格','情绪','压力','user','assistant','system','role','content'];
        if (generic.indexOf(text) !== -1) return false;
        return true;
    }

    // ── Time formatting ──
    function formatTime(isoStr) {
        if (!isoStr) return '';
        var d = new Date(isoStr);
        if (isNaN(d.getTime())) return '';

        var now = new Date();
        var pad = function (n) { return n < 10 ? '0' + n : '' + n; };
        var timeStr = pad(d.getHours()) + ':' + pad(d.getMinutes());

        var sameDay = d.getFullYear() === now.getFullYear()
            && d.getMonth() === now.getMonth()
            && d.getDate() === now.getDate();

        if (sameDay) {
            return timeStr;
        }

        var yesterday = new Date(now);
        yesterday.setDate(yesterday.getDate() - 1);
        var isYesterday = d.getFullYear() === yesterday.getFullYear()
            && d.getMonth() === yesterday.getMonth()
            && d.getDate() === yesterday.getDate();

        if (isYesterday) {
            return '昨天 ' + timeStr;
        }

        return pad(d.getMonth() + 1) + '/' + pad(d.getDate()) + ' ' + timeStr;
    }

    function updateMessageTime(el, isoStr) {
        var timeEl = el.querySelector('.message-time');
        if (!timeEl) return;
        if (isoStr) {
            timeEl.textContent = formatTime(isoStr);
        } else {
            // Fallback: use current time
            var now = new Date();
            var pad = function (n) { return n < 10 ? '0' + n : '' + n; };
            timeEl.textContent = pad(now.getHours()) + ':' + pad(now.getMinutes());
        }
    }

    // Try to get session_id from chat container
    var chatContainer = document.querySelector('.chat-container');
    var currentSessionId = chatContainer ? chatContainer.dataset.sessionId || null : null;

    var messageInput = document.getElementById('messageInput');
    var sendBtn = document.getElementById('sendBtn');
    var messageContainer = document.getElementById('messageContainer');
    var diaryNotice = document.getElementById('diaryNotice');
    var newSessionBtn = document.getElementById('newSessionBtn');
    var modeToggle = document.getElementById('modeToggle');
    var isLoading = false;

    // ── Perception Panel ──
    var perceptionPanel = document.getElementById('perceptionPanel');
    var perceptionToggle = document.getElementById('perceptionToggle');
    var perceptionBody = document.getElementById('perceptionBody');
    var emotionSummaryEl = document.getElementById('emotionSummary');
    var attributionCard = document.getElementById('attributionCard');
    var attributionSection = document.getElementById('attributionSection');
    var attributionText = document.getElementById('attributionText');
    var intensitySection = document.getElementById('intensitySection');
    var intensityBar = document.getElementById('intensityBar');
    var intensityChange = document.getElementById('intensityChange');
    var patternSection = document.getElementById('patternSection');
    var patternText = document.getElementById('patternText');
    var tipSection = document.getElementById('tipSection');
    var tipText = document.getElementById('tipText');
    var stageMessage = document.getElementById('stageMessage');

    // ── 新增面板元素 ──
    var currentEmotionSection = document.getElementById('currentEmotionSection');
    var emotionEmoji = document.getElementById('emotionEmoji');
    var emotionLabel = document.getElementById('emotionLabel');
    var emotionIntensityBar = document.getElementById('emotionIntensityBar');
    var emotionIntensityText = document.getElementById('emotionIntensityText');
    var keyNodesSection = document.getElementById('keyNodesSection');
    var keyNodesList = document.getElementById('keyNodesList');
    var panelInsightSection = document.getElementById('panelInsightSection');
    var panelInsightText = document.getElementById('panelInsightText');

    // 情绪队列
    var emotionHistory = [];       // [{emotion, intensity, attribution, stage}]
    var lastStage = '';
    var turnCount = 0;
    var keyNodes = [];

    var currentSessionId = null;   // 从页面获取

    // 从消息容器最后一条消息获取 session id
    // (页面初次渲染时从后端传入,实际在 stream 结束时从 meta 获取)

    // 展开/折叠
    if (perceptionToggle) {
        perceptionToggle.addEventListener('click', function () {
            perceptionBody.classList.toggle('perception-body-open');
            var btn = perceptionToggle;
            btn.textContent = perceptionBody.classList.contains('perception-body-open')
                ? '折叠 ▴' : '展开 ▾';
        });
    }

    // ── L1 规则比对(零成本,每轮执行) ──
    function updatePerceptionPanel(meta) {
        if (!perceptionPanel || !meta) {
            if (perceptionPanel) perceptionPanel.style.display = 'none';
            return;
        }

        var emotions = meta.emotion_tags || [];
        var intensity = meta.emotion_intensity || 0;
        var attribution = meta.attribution || '';
        var stage = meta.stage || '';
        var last = emotionHistory.length > 0 ? emotionHistory[emotionHistory.length - 1] : null;

        // 显示面板
        perceptionPanel.style.display = 'block';
        turnCount++;

        // ── 更新阶段指示器 ──
        if (stage) {
            updateStageDots(stage);
        }

        // ── 情绪转移检测 ──
        if (emotions.length > 0 && intensity > 0) {
            var currentEmotion = emotions[0];
            var changed = !last || last.emotion !== currentEmotion
                || Math.abs(last.intensity - intensity) >= 2;

            emotionHistory.push({
                emotion: currentEmotion,
                intensity: intensity,
                attribution: attribution,
                stage: stage,
            });

            if (changed) {
                updateCurrentEmotionCard(currentEmotion, intensity);
                drawEmotionCurve();
            }
        }

        // ── attribution 变化 / 情绪变化时追加关键节点 ──
        var attrToUse = attribution;
        // 兜底：LLM 没给归因但有情绪时，用情绪+简短描述
        if (!isValidAttribution(attrToUse) && emotions.length > 0) {
            attrToUse = emotions[0] + '情绪';
        }
        if (isValidAttribution(attrToUse) && (!last || last.attribution !== attrToUse)) {
            addKeyNode(attrToUse);
        }

        // ── 更新一句话洞察 ──
        updatePanelInsight(meta);

        // ── 强度显著下降(≥2)─
        if (last && intensity > 0 && last.intensity - intensity >= 2) {
            intensitySection.style.display = 'block';
            intensityBar.textContent = last.intensity + ' → ' + intensity;
            intensityChange.textContent = '↓ 有所缓解';
            intensityChange.className = 'intensity-change positive';
        } else if (last && intensity > 0 && intensity - last.intensity >= 2) {
            intensitySection.style.display = 'block';
            intensityBar.textContent = last.intensity + ' → ' + intensity;
            intensityChange.textContent = '↑ 强度增加';
            intensityChange.className = 'intensity-change negative';
        }

        // ── 归因浮现（含兜底） ──
        var displayAttr = attribution;
        if (!isValidAttribution(displayAttr) && emotions.length > 0) {
            displayAttr = emotions[0] + '情绪';
        }
        if (isValidAttribution(displayAttr) && (!last || last.attribution !== displayAttr)) {
            attributionSection.style.display = 'block';
            attributionText.textContent = displayAttr;
            attributionCard.style.display = 'flex';
        }

        // ── 阶段推进 ──
        if (stage && stage !== lastStage) {
            lastStage = stage;
        }

        // ── 阶段温馨文案 ──
        (function() {
            var stageMsg = meta.stage_message || '';
            if (stageMsg && stageMessage) {
                stageMessage.textContent = '💬 ' + stageMsg;
                stageMessage.style.display = 'block';
            } else if (stage && stageMessage && stage !== lastStage) {
                var fbs = {'empathy':'我在这里陪着你，慢慢说','attribution':'你已经开始理解自己了','challenge':'换个角度看看，也许有新的发现','closure':'今天的觉察，都在帮你更了解自己'};
                stageMessage.textContent = '💬 ' + (fbs[stage] || '');
                stageMessage.style.display = 'block';
            }
        })();

        // 如果已到 closure 阶段,异步触发 L3
        if (stage === 'closure') {
            scheduleL3PatternMatch();
        }

        // 持久化面板状态,刷新页面后保留
        savePanelState();
    }

    // ── 阶段圆点 ──
    var stageDots = document.querySelectorAll('.stage-dot');
    function updateStageDots(stage) {
        if (!stageDots.length) return;
        var order = ['empathy','attribution','challenge','closure'];
        var idx = order.indexOf(stage);
        if (idx === -1) return;
        stageDots.forEach(function (dot) {
            var dotIdx = order.indexOf(dot.dataset.stage);
            if (dotIdx >= 0 && dotIdx <= idx) {
                dot.classList.add('active');
            }
        });
    }

    // ── 情绪曲线绘制(Canvas) ──
    function drawEmotionCurve() {
        var canvas = document.getElementById('emotionCurve');
        if (!canvas) return;
        var ctx = canvas.getContext('2d');
        var w = canvas.width;
        var h = canvas.height;
        ctx.clearRect(0, 0, w, h);

        if (emotionHistory.length < 1) return;

        var data = emotionHistory;
        var padding = 10;
        var chartW = w - padding * 2;
        var chartH = h - padding * 2;

        // 强度映射:1→底部,5→顶部
        var maxIntensity = 5;
        var points = data.map(function (d, i) {
            var x = padding + (i / Math.max(data.length - 1, 1)) * chartW;
            var y = padding + chartH - (d.intensity / maxIntensity) * chartH;
            return {x: x, y: y, emotion: d.emotion, intensity: d.intensity};
        });

        // 画连线
        ctx.beginPath();
        ctx.strokeStyle = '#5B8DB8';
        ctx.lineWidth = 2;
        ctx.moveTo(points[0].x, points[0].y);
        for (var i = 1; i < points.length; i++) {
            ctx.lineTo(points[i].x, points[i].y);
        }
        ctx.stroke();

        // 画点
        var emotionColors = {
            '焦虑': '#E8A020', '压力': '#D4911A', '委屈': '#B38B5B',
            '愤怒': '#C0392B', '沮丧': '#7F8C8D', '无力': '#95A5A6',
            '开心': '#27AE60', '自豪': '#2980B9', '放松': '#1ABC9C',
            '失落': '#8E44AD', '不安': '#E67E22', '困惑': '#F39C12',
            '绝望': '#C0392B', '悲伤': '#5D6D7E', '自我怀疑': '#AAB7B8',
            '觉察': '#2ECC71', '思考': '#3498DB',
        };

        points.forEach(function (p) {
            ctx.beginPath();
            var color = emotionColors[p.emotion] || '#888';
            ctx.fillStyle = color;
            ctx.arc(p.x, p.y, 4, 0, Math.PI * 2);
            ctx.fill();

            // 标签
            ctx.fillStyle = '#555';
            ctx.font = '9px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(p.emotion, p.x, p.y - 8);
        });

        // 更新总结文本
        if (data.length >= 2) {
            var first = data[0];
            var last2 = data[data.length - 1];
            var summary = '从' + first.emotion + '(' + first.intensity + ')';
            if (last2.intensity < first.intensity) {
                summary += ' 降到 ' + last2.emotion + '(' + last2.intensity + ') ↓';
            } else if (last2.intensity > first.intensity) {
                summary += ' 升到 ' + last2.emotion + '(' + last2.intensity + ') ↑';
            } else {
                summary += ' → ' + last2.emotion + '(' + last2.intensity + ')';
            }
            emotionSummaryEl.textContent = summary;
        } else if (data.length === 1) {
            emotionSummaryEl.textContent = data[0].emotion + '(' + data[0].intensity + '/5)';
        }
    }

    // ── L2 分析结果处理(由 SSE analysis 事件驱动,不再独立 HTTP 请求) ──
    function applyAnalysisResults(data) {
        if (!data) return;
        if (data.emotion_summary && emotionSummaryEl) {
            emotionSummaryEl.textContent = data.emotion_summary;
        }
        if (data.pattern_match && patternSection) {
            patternSection.style.display = 'block';
            patternText.textContent = data.pattern_match;
        }
        if (data.actionable_tip && tipSection) {
            tipSection.style.display = 'block';
            tipText.textContent = data.actionable_tip;
        }
    }

    // ── L3 异步跨会话模式匹配 ──
    var l3Timer = null;
    function scheduleL3PatternMatch() {
        if (l3Timer) clearTimeout(l3Timer);
        l3Timer = setTimeout(function () {
            // L3 由后端在 analyze 端点内部自动触发
            // 这里只是记录
        }, 10000);
    }

    // ── 当前情绪大卡 ──
    function updateCurrentEmotionCard(emotion, intensity) {
        if (!currentEmotionSection || !emotionEmoji || !emotionLabel) return;
        currentEmotionSection.style.display = 'block';
        var emoji = EMOTION_EMOJI[emotion] || '😐';
        var col = EMOTION_COLORS[emotion] || '#888';
        emotionEmoji.textContent = emoji;
        emotionLabel.textContent = emotion;
        emotionIntensityBar.style.width = (intensity / 5 * 100) + '%';
        emotionIntensityBar.style.background = col;
        var t = intensity >= 4 ? '较强' : intensity >= 3 ? '中等' : intensity >= 2 ? '较低' : '轻微';
        emotionIntensityText.textContent = intensity + '/5 ' + t;
        currentEmotionSection.style.borderLeft = '3px solid ' + col;
        currentEmotionSection.style.background = col + '18';
    }

    // ── 一句话洞察（纯规则，不调后端） ──
    function updatePanelInsight(meta) {
        if (!panelInsightSection || !panelInsightText) return;
        panelInsightSection.style.display = 'block';
        var emotions = meta.emotion_tags || [];
        var emotion = emotions[0] || '';
        var intensity = meta.emotion_intensity || 0;
        var attribution = meta.attribution || '';
        var stage = meta.stage || '';
        var keyNodeCount = keyNodes.length;
        var draft = meta.insight_draft || '';
        var text = '';
        if (stage === 'closure') {
            text = draft ? '今天最重要的发现：' + draft.slice(0, 50) : '今天聊完了，感觉怎么样？';
        } else if (attribution && keyNodeCount >= 2) {
            text = '这已经是第' + keyNodeCount + '次提到同样的归因了——这不是巧合。';
        } else if (attribution) {
            text = '你找到了根源：' + attribution.slice(0, 30);
        } else if (intensity >= 4) {
            text = emotion + '的强度比较高，我们慢慢来。';
        } else if (intensity <= 2 && emotionHistory.length > 0) {
            text = emotion + '的强度在降低，这是一个好的信号。';
        } else if (emotion) {
            text = '你感觉到了' + emotion + '。';
        }
        if (text) {
            panelInsightText.textContent = text;
        }
    }

    // ── 关键节点 ──
    function addKeyNode(text) {
        if (!keyNodesSection || !keyNodesList || !isValidAttribution(text)) return;
        keyNodesSection.style.display = 'block';
        for (var i = 0; i < keyNodes.length; i++) {
            if (keyNodes[i] === text) return;
        }
        keyNodes.push(text);
        var div = document.createElement('div');
        div.className = 'key-node-item';
        div.innerHTML = '<span class="key-node-dot">🔍</span><span class="key-node-text">' + text + '</span>';
        keyNodesList.appendChild(div);
    }

    // ── Emoji/Color 映射 ──
    var EMOTION_EMOJI = {
        '\u7126\u8651':'😰',
        '\u59D4\u5C48':'🥺','\u6124\u6012':'😠','\u751F\u6C14':'😤','\u70E6\u8E81':'😣',
        '\u60B2\u4F24':'😢','\u96BE\u8FC7':'😢','\u5931\u843D':'😿',
        '\u5F00\u5FC3':'😊','\u9AD8\u5174':'🎉','\u6FC0\u52A8':'🤩','\u611F\u52A8':'🥹',
        '\u653E\u677E':'😌','\u5E73\u9759':'😐',
        '\u671F\u5F85':'✨','\u597D\u5947':'🤔','\u56F0\u60D1':'🤨','\u601D\u8003':'🧐',
        '\u89C9\u5BDF':'💡','\u75B2\u60EB':'😴',
    };
    var EMOTION_COLORS = {
        '\u7126\u8651':'#E8A020',
        '\u59D4\u5C48':'#B38B5B','\u6124\u6012':'#C0392B','\u751F\u6C14':'#D35400','\u70E6\u8E81':'#E67E22',
        '\u60B2\u4F24':'#5D6D7E','\u96BE\u8FC7':'#5D6D7E','\u5931\u843D':'#8E44AD',
        '\u5F00\u5FC3':'#27AE60','\u9AD8\u5174':'#2ECC71','\u6FC0\u52A8':'#3498DB','\u611F\u52A8':'#1ABC9C',
        '\u653E\u677E':'#1ABC9C','\u5E73\u9759':'#95A5A6',
        '\u671F\u5F85':'#9B59B6','\u597D\u5947':'#3498DB','\u56F0\u60D1':'#F39C12','\u601D\u8003':'#2C3E50',
        '\u89C9\u5BDF':'#2ECC71','\u75B2\u60EB':'#7F8C8D',
    };

    // ── 持久化面板状态 ──
    var PANEL_STORAGE_KEY = 'xiaoxu_panel_state';

    function savePanelState() {
        try {
            var activeDots = [];
            stageDots.forEach(function (dot) {
                if (dot.classList.contains('active')) {
                    activeDots.push(dot.dataset.stage);
                }
            });
            var state = {
                emotionHistory: emotionHistory,
                lastStage: lastStage,
                turnCount: turnCount,
                keyNodes: keyNodes,
                activeStages: activeDots,
                panelVisible: perceptionPanel ? perceptionPanel.style.display === 'block' : false,
                bodyOpen: perceptionBody ? perceptionBody.classList.contains('perception-body-open') : false,
                attributionVisible: attributionSection ? attributionSection.style.display === 'block' : false,
                attributionText: attributionText ? attributionText.textContent : '',
                intensityVisible: intensitySection ? intensitySection.style.display === 'block' : false,
                intensityBarText: intensityBar ? intensityBar.textContent : '',
                intensityChangeText: intensityChange ? intensityChange.textContent : '',
                intensityChangeClass: intensityChange ? intensityChange.className : '',
                patternVisible: patternSection ? patternSection.style.display === 'block' : false,
                patternText: patternText ? patternText.textContent : '',
                tipVisible: tipSection ? tipSection.style.display === 'block' : false,
                tipText: tipText ? tipText.textContent : '',
                emotionSummary: emotionSummaryEl ? emotionSummaryEl.textContent : '',
                stageMessage: stageMessage ? stageMessage.textContent : '',
            };
            localStorage.setItem(PANEL_STORAGE_KEY, JSON.stringify(state));
        } catch (e) {
            // localStorage may be unavailable
        }
    }

    function restorePanelState() {
        try {
            var raw = localStorage.getItem(PANEL_STORAGE_KEY);
            if (!raw) return;

            // ── Fix: 空对话不恢复旧面板数据 ──
            // 检查当前页面是否真的有聊天内容（除了 proactive msg 之外的对话消息）
            var hasUserMessage = Array.from(document.querySelectorAll('#messageContainer .message-user')).length > 0;
            var hasNonProactiveAssistantMessage = Array.from(document.querySelectorAll('#messageContainer .message-assistant')).filter(function(el) {
                return !el.classList.contains('proactive-msg') && !el.querySelector('.proactive-msg');
            }).length > 0;
            if (!hasUserMessage && !hasNonProactiveAssistantMessage) {
                // 新用户、新对话, 清除旧的 localStorage 残留
                localStorage.removeItem(PANEL_STORAGE_KEY);
                return;
            }
            var state = JSON.parse(raw);

            // 恢复变量
            if (state.emotionHistory && state.emotionHistory.length > 0) {
                emotionHistory = state.emotionHistory;
                if (perceptionPanel) perceptionPanel.style.display = 'block';
                var lastPt = emotionHistory[emotionHistory.length - 1];
                updateCurrentEmotionCard(lastPt.emotion, lastPt.intensity);
            }
            if (state.lastStage) lastStage = state.lastStage;
            if (state.turnCount) turnCount = state.turnCount;
            if (state.keyNodes && state.keyNodes.length > 0) {
                keyNodes = state.keyNodes;
                keyNodesSection.style.display = 'block';
                keyNodesList.innerHTML = '';
                for (var i = 0; i < keyNodes.length; i++) {
                    if (!isValidAttribution(keyNodes[i])) continue;
                    var d = document.createElement('div');
                    d.className = 'key-node-item';
                    d.innerHTML = '<span class="key-node-dot">🔍</span><span class="key-node-text">' + keyNodes[i] + '</span>';
                    keyNodesList.appendChild(d);
                }
            }

            // 恢复面板可见
            if (state.panelVisible && perceptionPanel) {
                perceptionPanel.style.display = 'block';
            }

            // 恢复展开/折叠
            if (perceptionBody && state.bodyOpen) {
                perceptionBody.classList.add('perception-body-open');
                if (perceptionToggle) perceptionToggle.textContent = '折叠 ▴';
            }

            // 恢复阶段圆点
            if (state.activeStages) {
                state.activeStages.forEach(function (stage) {
                    stageDots.forEach(function (dot) {
                        if (dot.dataset.stage === stage) {
                            dot.classList.add('active');
                        }
                    });
                });
            }

            // 恢复归因面板
            if (state.attributionVisible && attributionSection) {
                attributionSection.style.display = 'block';
                attributionCard.style.display = 'flex';
                if (isValidAttribution(state.attributionText)) attributionText.textContent = state.attributionText;
            }

            // 恢复强度面板
            if (state.intensityVisible && intensitySection) {
                intensitySection.style.display = 'block';
                if (state.intensityBarText) intensityBar.textContent = state.intensityBarText;
                if (state.intensityChangeText) intensityChange.textContent = state.intensityChangeText;
                if (state.intensityChangeClass) intensityChange.className = state.intensityChangeClass;
            }

            // 恢复模式面板
            if (state.patternVisible && patternSection) {
                patternSection.style.display = 'block';
                if (state.patternText) patternText.textContent = state.patternText;
            }

            // 恢复建议面板
            if (state.tipVisible && tipSection) {
                tipSection.style.display = 'block';
                if (state.tipText) tipText.textContent = state.tipText;
            }

            // 恢复情绪曲线
            if (state.emotionSummary) {
                emotionSummaryEl.textContent = state.emotionSummary;
            }
            // 恢复阶段文案
            if (state.stageMessage && stageMessage) {
                stageMessage.textContent = state.stageMessage;
                stageMessage.style.display = 'block';
            }
            if (emotionHistory.length > 0) {
                drawEmotionCurve();
            }
        } catch (e) {
            // Ignore restore errors
        }
    }

    function clearPanelState() {
        try {
            localStorage.removeItem(PANEL_STORAGE_KEY);
        } catch (e) {
            // ignore
        }
    }

    // ── 对外暴露 updatePerceptionPanel 供 stream 回调调用 ──
    // (stream 回调使用 updatePerceptionPanel(data.content) 调用)

    if (messageInput) {
        messageInput.addEventListener('input', function () {
            this.style.height = 'auto';
            this.style.height = Math.min(this.scrollHeight, 120) + 'px';
        });
        messageInput.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
    }

    // Suggestion chips
    document.addEventListener('click', function (e) {
        var chip = e.target.closest('.suggestion-chip');
        if (chip && messageInput) {
            messageInput.value = chip.dataset.text;
            sendMessage();
        }
    });

    function hideGuide() {
        var guide = document.getElementById('emptyGuide');
        if (guide) guide.style.display = 'none';
    }

    function resetLoading() {
        isLoading = false;
        if (sendBtn) sendBtn.disabled = false;
        if (messageInput) messageInput.focus();
    }

    function sendMessage() {
        if (!messageInput) return;
        var text = messageInput.value.trim();
        if (!text || isLoading) return;

        isLoading = true;
        sendBtn.disabled = true;
        messageInput.value = '';
        messageInput.style.height = 'auto';
        if (diaryNotice) diaryNotice.style.display = 'none';
        hideGuide();

        addMessage('user', text);

        // Safety: force-reset loading after 30s (prevent stuck button)
        var safetyTimer = setTimeout(function() {
            if (isLoading) {
                resetLoading();
            }
        }, 30000);

        // Try streaming first, fall back to non-streaming
        var streamingSupported = typeof ReadableStream !== 'undefined';
        if (streamingSupported && fetch) {
            sendMessageStream(text, safetyTimer);
        } else {
            clearTimeout(safetyTimer);
            sendMessageLegacy(text);
        }
    }

    function sendMessageStream(text, safetyTimer) {
        var assistantMsg = null;
        var assistantContent = null;
        var accumulatedText = '';
        var streamDone = false;
        var firstTextReceived = false;

        // Show typing dots immediately so user knows something is happening
        addTypingIndicator();

        function done() {
            if (streamDone) return;
            streamDone = true;
            if (!firstTextReceived) {
                // Stream ended without any text - remove typing dots
                removeTypingIndicator();
            }
            clearTimeout(safetyTimer);
            resetLoading();
        }

        fetch('/chat/api/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, stream: true }),
        })
        .then(function(response) {
            if (!response.ok) {
                throw new Error('HTTP ' + response.status);
            }
            var reader = response.body.getReader();
            var decoder = new TextDecoder();

            function readChunk() {
                return reader.read().then(function(result) {
                    if (result.done) {
                        done();
                        return;
                    }

                    var chunk = decoder.decode(result.value, {stream: true});
                    // Handle SSE: events are separated by \n\n
                    var parts = chunk.split('\n\n');
                    for (var p = 0; p < parts.length; p++) {
                        var part = parts[p].trim();
                        if (!part || !part.startsWith('data: ')) continue;

                        try {
                            var data = JSON.parse(part.slice(6));
                            if (data.type === 'session_id') {
                                currentSessionId = data.content;
                            } else if (data.type === 'text') {
                                var content = data.content.replace(/\\n/g, '\n').replace(/\\r/g, '\r');
                                accumulatedText += content;
                                var displayText = cleanResponseText(accumulatedText);
                                if (!assistantMsg) {
                                    // First text chunk: replace typing dots with real message
                                    removeTypingIndicator();
                                    firstTextReceived = true;
                                    assistantMsg = createAssistantMessage('');
                                    assistantContent = assistantMsg.querySelector('.message-text');
                                }
                                if (assistantContent) {
                                    assistantContent.textContent = displayText || '...';
                                }
                                scrollToBottom();
                            } else if (data.type === 'meta') {
                                updatePerceptionPanel(data.content);
                            } else if (data.type === 'diary') {
                                if (diaryNotice) diaryNotice.style.display = 'flex';
                            } else if (data.type === 'analysis') {
                                applyAnalysisResults(data.content);
                            } else if (data.type === 'done' || data.type === 'error') {
                                done();
                            }
                        } catch(e) {
                            console.warn('SSE parse:', e.message);
                        }
                    }

                    return readChunk();
                });
            }

            return readChunk();
        })
        .catch(function() {
            done();
            removeTypingIndicator();
            if (!assistantMsg) {
                addMessage('assistant', '小绪暂时无法回复,请稍后再试。');
            }
        });
    }

    function createAssistantMessage(text) {
        if (!messageContainer) return null;
        var div = document.createElement('div');
        div.className = 'message message-assistant';
        div.innerHTML = '<div class="message-avatar">🌱</div>'
            + '<div class="message-content">'
            + '<div class="message-text"></div>'
            + '<div class="message-time"></div>'
            + '</div>';
        messageContainer.appendChild(div);
        updateMessageTime(div);
        scrollToBottom();
        return div;
    }

    function sendMessageLegacy(text) {
        addTypingIndicator();

        fetch('/chat/api/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text }),
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            removeTypingIndicator();
            addMessage('assistant', data.response);
            updatePerceptionPanel(data.structured_meta);
            if (data.session_id) currentSessionId = data.session_id;
            if (data.diary && diaryNotice) {
                diaryNotice.style.display = 'flex';
            }
        })
        .catch(function () {
            removeTypingIndicator();
            addMessage('assistant', '小绪暂时无法回复,请稍后再试。');
        })
        .finally(function () {
            isLoading = false;
            sendBtn.disabled = false;
            if (messageInput) messageInput.focus();
        });
    }

    function addMessage(role, text, created_at) {
        if (!messageContainer) return;
        var div = document.createElement('div');
        div.className = 'message ' + (role === 'user' ? 'message-user' : 'message-assistant');

        var avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.textContent = role === 'user' ? '🧑' : '🌱';

        var contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';

        var textDiv = document.createElement('div');
        textDiv.className = 'message-text';
        textDiv.textContent = cleanResponseText(text);
        contentDiv.appendChild(textDiv);

        var timeDiv = document.createElement('div');
        timeDiv.className = 'message-time';
        contentDiv.appendChild(timeDiv);

        div.appendChild(avatar);
        div.appendChild(contentDiv);
        messageContainer.appendChild(div);

        updateMessageTime(div, created_at);
        scrollToBottom();
    }

    // ── Typing Indicator ──
    var typingDiv = null;

    function addTypingIndicator() {
        if (!messageContainer) return;
        typingDiv = document.createElement('div');
        typingDiv.className = 'message message-assistant';
        typingDiv.id = 'typingIndicator';
        typingDiv.innerHTML = '<div class="message-avatar">🌱</div>'
            + '<div class="message-content">'
            + '<div class="message-text typing-dots">'
            + '<span class="dot">.</span><span class="dot">.</span><span class="dot">.</span>'
            + '</div></div>';
        messageContainer.appendChild(typingDiv);
        scrollToBottom();
    }

    function removeTypingIndicator() {
        var el = document.getElementById('typingIndicator');
        if (el) el.remove();
        typingDiv = null;
    }

    // ── Clean structured metadata from visible text (frontend belt-and-suspenders) ──
    function cleanResponseText(text) {
        // Strip ---STR... (any variant: ---STRUCTURED, ---STRUCTURE, etc.) up to ---END or end
        return text.replace(/---STR[A-Z]*[\s\S]*?(?:---END|$)/g, '').trim();
    }

    function scrollToBottom() {
        if (messageContainer) {
            messageContainer.scrollTop = messageContainer.scrollHeight;
        }
    }

    if (sendBtn) { sendBtn.addEventListener('click', sendMessage); }

    if (newSessionBtn) {
        newSessionBtn.addEventListener('click', function () {
            if (isLoading) return;
            clearPanelState();
            fetch('/chat/api/new', { method: 'POST' })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    window.location.href = data.redirect || '/chat';
                });
        });
    }

    if (modeToggle) {
        modeToggle.addEventListener('click', function () {
            var current = modeToggle.textContent.indexOf('探索') >= 0 ? 'exploring' : 'listening';
            var next = current === 'exploring' ? 'listening' : 'exploring';
            fetch('/chat/api/mode', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mode: next }),
            })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                modeToggle.textContent = data.mode === 'exploring'
                    ? '🔎 探索模式' : '👂 倾听模式';
            });
        });
    }

    // ── Fill timestamps for server-rendered messages ──
    var allMessages = document.querySelectorAll('#messageContainer .message');
    allMessages.forEach(function (el) {
        var created = el.dataset.created;
        updateMessageTime(el, created);
    });

    // 刷新页面后恢复面板状态
    restorePanelState();

    // 检查是否有新的月度总结
    checkMonthlyNotifications();

    scrollToBottom();

    // ── 月度总结主动推送 ──
    function checkMonthlyNotifications() {
        fetch('/monthly/api/notifications')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var list = data.new_summaries || [];
                if (list.length > 0) {
                    var noticeEl = document.getElementById('monthlyNotice');
                    if (!noticeEl) {
                        noticeEl = document.createElement('div');
                        noticeEl.id = 'monthlyNotice';
                        noticeEl.className = 'diary-notice';
                        var diaryNoticeEl = document.getElementById('diaryNotice');
                        var ref = diaryNoticeEl || document.querySelector('.input-area');
                        if (ref) {
                            ref.parentNode.insertBefore(noticeEl, ref);
                        }
                    }
                    noticeEl.style.display = 'flex';
                    noticeEl.innerHTML = '<span>📊 小绪为你整理了新的成长总结</span>'
                        + '<a href="/monthly" class="notice-link">去看看 →</a>';

                    // Auto-mark as read after 5 seconds
                    setTimeout(function () {
                        fetch('/monthly/api/notifications/read', { method: 'POST' });
                    }, 5000);
                }
            })
            .catch(function () { /* ignore */ });
    }

    // ── 语音输入模块 ──
    var voiceBtn = document.getElementById('voiceBtn');
    var recognition = null;
    var isRecording = false;

    var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition && voiceBtn) {
        recognition = new SpeechRecognition();
        recognition.lang = 'zh-CN';
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.maxAlternatives = 1;

        voiceBtn.addEventListener('click', function () {
            if (isRecording) {
                recognition.stop();
                return;
            }
            isRecording = true;
            voiceBtn.classList.add('recording');
            voiceBtn.textContent = '⏺';
            recognition.start();
        });

        recognition.onresult = function (e) {
            var text = e.results[0][0].transcript;
            var input = document.getElementById('messageInput');
            if (input) {
                input.value = text;
                input.style.height = 'auto';
                input.style.height = input.scrollHeight + 'px';
            }
        };

        recognition.onend = function () {
            isRecording = false;
            if (voiceBtn) {
                voiceBtn.classList.remove('recording');
                voiceBtn.textContent = '🎤';
            }
        };

        recognition.onerror = function () {
            isRecording = false;
            if (voiceBtn) {
                voiceBtn.classList.remove('recording');
                voiceBtn.textContent = '🎤';
            }
        };
    } else if (voiceBtn) {
        voiceBtn.style.display = 'none';
    }
})();
