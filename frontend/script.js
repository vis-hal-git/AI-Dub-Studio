const API_BASE_URL = 'http://127.0.0.1:8000/api/v1';

document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const form = document.getElementById('dubbing-form');
    const fileInput = document.getElementById('video-file');
    const dropZone = document.getElementById('drop-zone');
    const selectedFileName = document.getElementById('selected-file-name');
    const submitBtn = document.getElementById('submit-btn');
    
    const sections = {
        upload: document.getElementById('upload-section'),
        status: document.getElementById('status-section'),
        result: document.getElementById('result-section')
    };

    const statusUI = {
        badge: document.getElementById('job-status-badge'),
        stage: document.getElementById('current-stage'),
        progressFill: document.getElementById('progress-fill'),
        progressText: document.getElementById('progress-percent'),
        speakersPanel: document.getElementById('speakers-panel'),
        speakersList: document.getElementById('speakers-list')
    };

    const resultUI = {
        newJobBtn: document.getElementById('new-job-btn'),
        transcriptPanel: document.getElementById('transcript-panel'),
        transcriptList: document.getElementById('transcript-list')
    };

    let pollingInterval = null;

    // File Drag & Drop Handling
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.add('dragover'), false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.remove('dragover'), false);
    });

    dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        handleFiles(files);
    });

    fileInput.addEventListener('change', function() {
        handleFiles(this.files);
    });

    function handleFiles(files) {
        if (files.length > 0) {
            const file = files[0];
            
            // Basic validation
            if (!file.type.startsWith('video/')) {
                showToast('Please select a valid video file.', true);
                return;
            }
            if (file.size > 500 * 1024 * 1024) {
                showToast('File size exceeds 500MB limit.', true);
                return;
            }

            // Manually set files on input if dropped
            const dataTransfer = new DataTransfer();
            dataTransfer.items.add(file);
            fileInput.files = dataTransfer.files;

            selectedFileName.textContent = file.name;
            selectedFileName.classList.remove('hidden');
        }
    }

    // Form Submission
    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        if (!fileInput.files || fileInput.files.length === 0) {
            showToast('Please select a video file first.', true);
            return;
        }

        submitBtn.disabled = true;
        submitBtn.innerHTML = 'Uploading...';

        const formData = new FormData(form);

        try {
            const response = await fetch(`${API_BASE_URL}/jobs`, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                throw new Error(errData.detail || 'Failed to create job');
            }

            const data = await response.json();
            
            // Switch sections
            switchSection('status');
            startPolling(data.job_id);

        } catch (error) {
            showToast(error.message, true);
            submitBtn.disabled = false;
            submitBtn.innerHTML = 'Start Dubbing';
        }
    });

    // Polling Job Status
    function startPolling(jobId) {
        // Initial fetch
        fetchStatus(jobId);
        
        // Poll every 3 seconds
        pollingInterval = setInterval(() => {
            fetchStatus(jobId);
        }, 3000);
    }

    async function fetchStatus(jobId) {
        try {
            const response = await fetch(`${API_BASE_URL}/jobs/${jobId}`);
            
            if (!response.ok) {
                throw new Error('Failed to fetch status');
            }

            const data = await response.json();
            updateStatusUI(data);

            if (data.status === 'completed' || data.status === 'failed') {
                clearInterval(pollingInterval);
                
                if (data.status === 'completed') {
                    setTimeout(() => {
                        switchSection('result');
                        resultUI.downloadBtn.href = `${API_BASE_URL}/jobs/${jobId}/download`;
                        resultUI.downloadBtn.download = '';
                        
                        // Render transcript if available
                        if (data.translation && data.translation.length > 0) {
                            renderTranscript(data.translation);
                            resultUI.transcriptPanel.classList.remove('hidden');
                        } else {
                            resultUI.transcriptPanel.classList.add('hidden');
                        }
                    }, 1500); // Wait a moment so user sees 100%
                } else if (data.status === 'failed') {
                    showToast(`Job failed: ${data.error || 'Unknown error'}`, true);
                    switchSection('upload');
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = 'Try Again';
                }
            }

        } catch (error) {
            console.error('Polling error:', error);
        }
    }

    function updateStatusUI(data) {
        statusUI.badge.textContent = data.status.replace('_', ' ');
        statusUI.badge.setAttribute('data-status', data.status);
        
        statusUI.stage.textContent = data.current_stage || `Processing (${data.status})...`;
        
        const progress = data.progress || 0;
        statusUI.progressFill.style.width = `${progress}%`;
        statusUI.progressText.textContent = `${Math.round(progress)}%`;

        // Update speakers if they exist
        if (data.speakers_detected && data.speakers_detected.length > 0) {
            statusUI.speakersPanel.classList.remove('hidden');
            
            // Rebuild list if changed
            if (statusUI.speakersList.children.length !== data.speakers_detected.length) {
                statusUI.speakersList.innerHTML = '';
                data.speakers_detected.forEach(speaker => {
                    const li = document.createElement('li');
                    li.className = 'speaker-item';
                    li.innerHTML = `
                        <span class="speaker-id">${speaker.speaker_id}</span>
                        <span class="speaker-voice">Voice: ${speaker.voice_assigned}</span>
                    `;
                    statusUI.speakersList.appendChild(li);
                });
            }
        }
    }

    // New Job Button
    resultUI.newJobBtn.addEventListener('click', () => {
        form.reset();
        selectedFileName.classList.add('hidden');
        statusUI.speakersPanel.classList.add('hidden');
        statusUI.speakersList.innerHTML = '';
        resultUI.transcriptPanel.classList.add('hidden');
        resultUI.transcriptList.innerHTML = '';
        statusUI.progressFill.style.width = '0%';
        statusUI.progressText.textContent = '0%';
        submitBtn.disabled = false;
        submitBtn.innerHTML = 'Start Dubbing';
        switchSection('upload');
    });

    // Helpers
    function renderTranscript(segments) {
        resultUI.transcriptList.innerHTML = '';
        segments.forEach(seg => {
            const div = document.createElement('div');
            div.className = 'transcript-item';
            
            const start = seg.start_time.toFixed(1);
            const end = seg.end_time.toFixed(1);
            
            div.innerHTML = `
                <div class="transcript-meta">
                    <span class="transcript-speaker">${seg.speaker_id}</span>
                    <span class="transcript-time">${start}s - ${end}s</span>
                </div>
                <div class="transcript-text">${seg.translated_text}</div>
                <div class="transcript-original">${seg.original_text}</div>
            `;
            resultUI.transcriptList.appendChild(div);
        });
    }

    function switchSection(sectionId) {
        Object.values(sections).forEach(sec => sec.classList.add('hidden'));
        sections[sectionId].classList.remove('hidden');
    }

    function showToast(message, isError = false) {
        const toast = document.getElementById('toast');
        toast.textContent = message;
        
        if (isError) {
            toast.classList.add('error');
        } else {
            toast.classList.remove('error');
        }
        
        toast.classList.remove('hidden');
        
        // Trigger reflow for transition
        void toast.offsetWidth;
        
        toast.classList.add('show');
        
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.classList.add('hidden'), 300); // Wait for transition
        }, 5000);
    }
});
