// cc-boss front-end: task submission, voice input, WebSocket live logs

(function() {
    'use strict';

    // --- Task submission ---
    const form = document.getElementById('task-form');
    const input = document.getElementById('task-input');
    const planBtn = document.getElementById('plan-btn');

    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const prompt = input.value.trim();
            if (!prompt) return;
            await submitTask(prompt);
            input.value = '';
        });
    }

    if (planBtn) {
        planBtn.addEventListener('click', async () => {
            const prompt = input.value.trim();
            if (!prompt) return;
            const res = await submitTask(prompt);
            if (res && res.id) {
                // Trigger plan generation
                await fetch(`/api/tasks/${res.id}/plan`, { method: 'POST' });
                location.reload();
            }
        });
    }

    async function submitTask(prompt, priority) {
        try {
            const res = await fetch('/api/tasks', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt, priority: priority || 0 }),
            });
            const data = await res.json();
            location.reload();
            return data;
        } catch (err) {
            console.error('Failed to submit task:', err);
        }
    }

    // --- Voice input (Web Speech API) ---
    const voiceBtn = document.getElementById('voice-btn');
    if (voiceBtn && ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window)) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        const recognition = new SpeechRecognition();
        recognition.lang = 'zh-CN';
        recognition.interimResults = true;
        recognition.continuous = false;

        let isRecording = false;

        voiceBtn.addEventListener('touchstart', (e) => {
            e.preventDefault();
            if (!isRecording) {
                recognition.start();
                isRecording = true;
                voiceBtn.classList.add('recording');
            }
        });

        voiceBtn.addEventListener('touchend', (e) => {
            e.preventDefault();
            if (isRecording) {
                recognition.stop();
                isRecording = false;
                voiceBtn.classList.remove('recording');
            }
        });

        // Mouse fallback for desktop
        voiceBtn.addEventListener('mousedown', () => {
            if (!isRecording) {
                recognition.start();
                isRecording = true;
                voiceBtn.classList.add('recording');
            }
        });

        voiceBtn.addEventListener('mouseup', () => {
            if (isRecording) {
                recognition.stop();
                isRecording = false;
                voiceBtn.classList.remove('recording');
            }
        });

        recognition.onresult = (e) => {
            const transcript = Array.from(e.results)
                .map(r => r[0].transcript)
                .join('');
            input.value = transcript;
        };

        recognition.onerror = (e) => {
            console.warn('Speech recognition error:', e.error);
            isRecording = false;
            voiceBtn.classList.remove('recording');
        };
    } else if (voiceBtn) {
        // No speech API available
        voiceBtn.style.display = 'none';
    }

    // --- WebSocket live logs ---
    const liveLog = document.getElementById('live-log');
    if (liveLog) {
        const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const ws = new WebSocket(`${proto}//${location.host}/ws`);

        ws.onmessage = (e) => {
            try {
                const data = JSON.parse(e.data);
                const line = document.createElement('div');
                line.className = 'log-line';
                line.textContent = `[#${data.task_id}] ${data.type}: ${data.content || ''}`;
                liveLog.appendChild(line);
                liveLog.classList.add('visible');
                liveLog.scrollTop = liveLog.scrollHeight;

                // Auto-hide after 10s of no new messages
                clearTimeout(liveLog._hideTimer);
                liveLog._hideTimer = setTimeout(() => {
                    liveLog.classList.remove('visible');
                }, 10000);

                // Update task card status in real-time
                updateTaskCard(data);
            } catch (err) {
                // ignore parse errors
            }
        };

        ws.onclose = () => {
            setTimeout(() => location.reload(), 3000);
        };
    }

    function updateTaskCard(data) {
        const card = document.querySelector(`.task-card[data-id="${data.task_id}"]`);
        if (!card) return;

        if (data.type === 'result') {
            // Task finished — reload to get final status
            setTimeout(() => location.reload(), 1000);
        }
    }

    // --- Auto-refresh worker status ---
    setInterval(async () => {
        try {
            const res = await fetch('/api/workers');
            const workers = await res.json();
            const bar = document.querySelector('.worker-bar');
            if (!bar) return;
            bar.innerHTML = workers.map(w => {
                const cls = w.current_task_id ? 'active' : 'idle';
                const label = w.current_task_id ? `W${w.worker_id} #${w.current_task_id}` : `W${w.worker_id}`;
                return `<span class="worker-chip ${cls}">${label}</span>`;
            }).join('');
        } catch (e) {
            // ignore
        }
    }, 5000);

})();
