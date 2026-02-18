import React, { useState, useEffect } from 'react';
import { setAuthToken } from './services/api';
import { api } from './services/api';
import { useAuth, useSession } from './hooks';
import { Sidebar } from './components/layout';
import { WelcomePage, WorkspacePage } from './pages';
import Login from './Login';

function App() {
  const { authUser, setAuthUser, logout } = useAuth();
  const {
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
  } = useSession(authUser);

  const [inputMessage, setInputMessage] = useState('');
  const [runData, setRunData] = useState(null);
  const [runFiles, setRunFiles] = useState({});
  const [loading, setLoading] = useState(false);
  const [githubRepo, setGithubRepo] = useState('');

  // Set auth token when user logs in
  useEffect(() => {
    if (authUser) {
      setAuthToken(authUser.token);
    }
  }, [authUser]);

  // Poll run status if a run is active
  useEffect(() => {
    let interval;
    if (runId && ['created', 'planning', 'applying'].includes(runData?.status)) {
      interval = setInterval(() => {
        fetchRunData(runId);
      }, 3000);
    }
    return () => clearInterval(interval);
  }, [runId, runData?.status]);

  const fetchRunData = async (id) => {
    try {
      const data = await api.getRun(id);
      setRunData(data);
      // If planned/completed, ensure we have files
      if (['planned', 'completed', 'reviewing', 'applying', 'applied'].includes(data.status)) {
        fetchRunFiles(id);
      }
    } catch (err) {
      console.error('Failed to fetch run data', err);
    }
  };

  const fetchRunFiles = async (id) => {
    try {
      const data = await api.getRunFiles(id);
      if (data.files) {
        setRunFiles(data.files);
      }
    } catch (err) {
      console.error('Failed to fetch files', err);
    }
  };

  // Navigation state
  const [activeTab, setActiveTab] = useState('chat');

  // Load files when switching to review tab if missing
  useEffect(() => {
    if (activeTab === 'review' && runId && Object.keys(runFiles).length === 0) {
      fetchRunFiles(runId);
    }
  }, [activeTab, runId, runFiles]);

  // Switch to review tab when run starts
  useEffect(() => {
    if (runId && activeTab === 'chat' && runData?.status === 'planning') {
      setActiveTab('review');
    }
  }, [runId, runData?.status]);

  const handleStartConversation = async (githubInfo) => {
    setLoading(true);
    try {
      const data = await api.createConversation(
        githubInfo.owner,
        githubInfo.repo,
        githubInfo.token,
        githubInfo.branch
      );
      setSessionId(data.session_id);
      setMessages([
        {
          role: 'assistant',
          content: data.bot_response,
          suggestions: data.suggestions || [],
        },
      ]);
      setIsComplete(false);
      setRunId(null);
      setRunData(null);
      setGithubRepo(githubInfo.repo);
      fetchSessions();
    } catch (err) {
      alert('Failed to start conversation: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSendMessage = async (msg = inputMessage) => {
    if (!msg.trim() || !sessionId) return;

    // Optimistic update
    const newUserMsg = { role: 'user', content: msg };
    setMessages((prev) => [...prev, newUserMsg]);
    setInputMessage('');
    setLoading(true);

    // Add placeholder for streaming bot response
    const botMsgIndex = messages.length + 1;
    setMessages((prev) => [...prev, { role: 'assistant', content: '', suggestions: [], isStreaming: true }]);

    try {
      let streamedContent = '';
      
      await api.streamMessage(
        sessionId,
        msg,
        // onChunk - called for each text chunk
        (chunk) => {
          streamedContent += chunk;
          setMessages((prev) => {
            const updated = [...prev];
            updated[botMsgIndex] = {
              role: 'assistant',
              content: streamedContent,
              suggestions: [],
              isStreaming: true
            };
            return updated;
          });
        },
        // onComplete - called when streaming finishes
        (data) => {
          setMessages((prev) => {
            const updated = [...prev];
            updated[botMsgIndex] = {
              role: 'assistant',
              content: streamedContent,
              suggestions: data.suggestions || [],
              isStreaming: false
            };
            return updated;
          });
          
          setIsComplete(data.is_complete);
          setCollectedParams(data.collected_parameters || {});
          
          if (data.run_id) {
            setRunId(data.run_id);
            fetchRunData(data.run_id);
          }
          
          setLoading(false);
        },
        // onError - called if streaming fails
        (error) => {
          console.error('Streaming failed:', error);
          setMessages((prev) => {
            const updated = [...prev];
            updated[botMsgIndex] = {
              role: 'assistant',
              content: `Error: ${error}`,
              suggestions: [],
              isStreaming: false
            };
            return updated;
          });
          setLoading(false);
        }
      );
    } catch (err) {
      console.error('Failed to send message:', err);
      setMessages((prev) => prev.slice(0, -1)); // Remove placeholder
      alert('Failed to send message: ' + err.message);
      setLoading(false);
    }
  };

  const handleLoadSession = async (id) => {
    setLoading(true);
    setRunData(null);
    setRunFiles({});
    try {
      const rid = await loadSession(id);
      if (rid) fetchRunData(rid);
    } catch (err) {
      alert('Failed to load session');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteSession = async (id) => {
    if (!confirm('Delete this session?')) return;
    try {
      await deleteSession(id);
    } catch (err) {
      alert('Failed to delete session');
    }
  };

  const handleGenerateTerraform = async () => {
    setLoading(true);
    try {
      const data = await api.generateTerraform(sessionId);
      setRunId(data.run_id);
      fetchRunData(data.run_id);
    } catch (err) {
      alert('Generation failed');
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    setAuthToken(null);
    logout();
    resetSession();
  };

  const handleNewChat = () => {
    resetSession();
    setGithubRepo('');
    setActiveTab('chat');
  };

  if (!authUser) {
    return <Login onLogin={setAuthUser} />;
  }

  return (
    <div className="app-container">
      <Sidebar
        sessions={sessions}
        activeSessionId={sessionId}
        onNewChat={handleNewChat}
        onSessionSelect={handleLoadSession}
        onSessionDelete={handleDeleteSession}
        userEmail={authUser.email}
        onLogout={handleLogout}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        hasRun={!!runId}
      />

      <main className="main-content">
        {!sessionId ? (
          <WelcomePage onStartConversation={handleStartConversation} loading={loading} />
        ) : (
          <WorkspacePage
            sessionId={sessionId}
            messages={messages}
            inputMessage={inputMessage}
            onInputChange={setInputMessage}
            onSendMessage={handleSendMessage}
            isComplete={isComplete}
            collectedParams={collectedParams}
            runId={runId}
            runData={runData}
            runFiles={runFiles}
            onGenerateTerraform={handleGenerateTerraform}
            onFetchRunData={fetchRunData}
            githubRepo={githubRepo}
            activeTab={activeTab}
            onTabChange={setActiveTab}
          />
        )}
      </main>
    </div>
  );
}

export default App;
