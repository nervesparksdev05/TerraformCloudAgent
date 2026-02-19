import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const client = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

// Initialize from localStorage
const storedAuth = localStorage.getItem('tca_auth');
if (storedAuth) {
    try {
        const { token } = JSON.parse(storedAuth);
        if (token) client.defaults.headers.common['Authorization'] = `Bearer ${token}`;
    } catch (e) {
        console.error('Failed to parse stored auth', e);
    }
}

// Helper to set auth header
export const setAuthToken = (token) => {
    if (token) {
        client.defaults.headers.common['Authorization'] = `Bearer ${token}`;
    } else {
        delete client.defaults.headers.common['Authorization'];
    }
};

export const api = {
    // Auth / User
    syncUser: async () => {
        const { data } = await client.post('/auth/sync-user');
        return data;
    },

    getMe: async () => {
        const { data } = await client.get('/auth/me');
        return data;
    },

    // Runs - edit
    editRunWithFeedback: async (runId, message) => {
        const { data } = await client.post(`/runs/${runId}/edit`, { message });
        return data;
    },

    updateRunFiles: async (runId, files) => {
        const { data } = await client.post(`/runs/${runId}/files`, files);
        return data;
    },

    // Conversations
    createConversation: async (owner, repo, githubToken = '', githubBranch = '') => {

        const params = { owner, repo };
        if (githubToken) params.github_token = githubToken;
        if (githubBranch) params.github_branch = githubBranch;
        const { data } = await client.post('/conversations', null, { params });
        return data;
    },

    getSessions: async (limit = 20) => {
        const { data } = await client.get('/sessions', { params: { limit } });
        return data;
    },

    getSession: async (sessionId) => {
        const { data } = await client.get(`/conversations/${sessionId}`);
        return data;
    },

    deleteSession: async (sessionId) => {
        const { data } = await client.delete(`/sessions/${sessionId}`);
        return data;
    },

    sendMessage: async (sessionId, message) => {
        const { data } = await client.post(`/conversations/${sessionId}/message`, { message });
        return data;
    },

    streamMessage: async (sessionId, message, onChunk, onComplete, onError) => {
        const token = client.defaults.headers.common['Authorization']?.replace('Bearer ', '');

        try {
            const response = await fetch(`${API_BASE_URL}/conversations/${sessionId}/message/stream`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(token ? { 'Authorization': `Bearer ${token}` } : {})
                },
                body: JSON.stringify({ message })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n\n');
                buffer = lines.pop(); // Keep incomplete line in buffer

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));

                            if (data.error) {
                                onError?.(data.error);
                                return;
                            }

                            if (data.content) {
                                onChunk?.(data.content);
                            }

                            if (data.done) {
                                onComplete?.(data);
                                return;
                            }
                        } catch (e) {
                            console.error('Failed to parse SSE data:', e);
                        }
                    }
                }
            }
        } catch (error) {
            console.error('Streaming error:', error);
            onError?.(error.message);
        }
    },

    generateTerraform: async (sessionId) => {
        const { data } = await client.post(`/conversations/${sessionId}/generate`);
        return data;
    },

    // Runs
    getRun: async (runId) => {
        const { data } = await client.get(`/runs/${runId}`);
        return data;
    },

    getRunFiles: async (runId) => {
        const { data } = await client.get(`/runs/${runId}/files`);
        return data;
    },

    approveRun: async (runId) => {
        const { data } = await client.post(`/runs/${runId}/approve`);
        return data;
    },

    rejectRun: async (runId) => {
        const { data } = await client.post(`/runs/${runId}/reject`);
        return data;
    },

    destroyRun: async (runId) => {
        const { data } = await client.post(`/runs/${runId}/destroy`);
        return data;
    },

    sendForApproval: async (runId) => {
        const { data } = await client.post(`/runs/${runId}/send-for-approval`);
        return data;
    },

    getApprovalStatus: async (runId) => {
        const { data } = await client.get(`/runs/${runId}/approval-status`);
        return data;
    },

    chatAboutRun: async (runId, message) => {
        const { data } = await client.post(`/runs/${runId}/chat`, { message });
        return data;
    },

    // Feedback
    submitFeedback: async (sessionId, messageIndex, score, comment = '') => {
        const { data } = await client.post('/feedback', {
            session_id: sessionId,
            message_index: messageIndex,
            score,
            comment,
        });
        return data;
    },
};

export default api;
