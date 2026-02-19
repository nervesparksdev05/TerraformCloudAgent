import { useState, useEffect } from 'react';
import { api } from '../services/api';

export const useSession = (authUser) => {
    const [sessions, setSessions] = useState([]);
    const [sessionId, setSessionId] = useState(null);
    const [messages, setMessages] = useState([]);
    const [isComplete, setIsComplete] = useState(false);
    const [collectedParams, setCollectedParams] = useState({});
    const [runId, setRunId] = useState(null);

    useEffect(() => {
        if (authUser) {
            fetchSessions();
        }
    }, [authUser]);

    const fetchSessions = async () => {
        try {
            const data = await api.getSessions();
            setSessions(data || []);
        } catch (err) {
            console.error('Failed to fetch sessions', err);
        }
    };

    const loadSession = async (id) => {
        try {
            const data = await api.getSession(id);
            setSessionId(id);
            setMessages(data.messages.filter((m) => ['user', 'assistant'].includes(m.role)));
            setIsComplete(data.is_complete);
            setCollectedParams(data.collected_parameters || {});
            const rid = data.run_ids && data.run_ids.length > 0 ? data.run_ids[data.run_ids.length - 1] : null;
            setRunId(rid);
            return rid;
        } catch (err) {
            console.error('Failed to load session', err);
            throw err;
        }
    };

    const deleteSession = async (id) => {
        try {
            await api.deleteSession(id);
            if (sessionId === id) {
                setSessionId(null);
                setMessages([]);
            }
            fetchSessions();
        } catch (err) {
            console.error('Failed to delete session', err);
            throw err;
        }
    };

    const resetSession = () => {
        setSessionId(null);
        setMessages([]);
        setRunId(null);
        setIsComplete(false);
        setCollectedParams({});
    };

    return {
        sessions,
        sessionId,
        messages,
        isComplete,
        collectedParams,
        runId,
        setSessionId,
        setMessages,
        setIsComplete,
        setCollectedParams,
        setRunId,
        fetchSessions,
        loadSession,
        deleteSession,
        resetSession,
    };
};

export default useSession;
