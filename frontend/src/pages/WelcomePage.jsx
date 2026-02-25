import React, { useState } from 'react';
import { Plus, Terminal, RefreshCw, Lock, GitBranch } from 'lucide-react';
import { Card, Input, Button } from '../components/common';

export const WelcomePage = ({ onStartConversation, loading }) => {
  const [githubUrl, setGithubUrl] = useState('');
  const [githubInfo, setGithubInfo] = useState({
    owner: '',
    repo: '',
    branch: '',
    token: '',
  });

  const handleStart = () => {
    if (githubInfo.owner && githubInfo.repo) {
      onStartConversation(githubInfo);
    }
  };

  const set = (key) => (e) => setGithubInfo({ ...githubInfo, [key]: e.target.value });

  const handleUrlChange = (e) => {
    const url = e.target.value;
    setGithubUrl(url);

    // Try to parse GitHub URL: https://github.com/owner/repo
    try {
      const match = url.match(/github\.com\/([^/]+)\/([^/.]+)/);
      if (match) {
        setGithubInfo(prev => ({
          ...prev,
          owner: match[1],
          repo: match[2]
        }));
      }
    } catch {
      // Ignore parse errors while typing
    }
  };

  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <Card className="w-full max-w-2xl animate-fade-in">
        <div className="text-center mb-8">
          <div
            className="inline-flex p-4 rounded-2xl mb-4"
            style={{ background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' }}
          >
            <Terminal size={48} className="text-white" />
          </div>
          <h1 className="text-3xl mb-2 font-bold">Welcome to Terraform Agent</h1>
          <p className="text-gray-400">
            Deploy complex architectures directly from your GitHub READMEs.
          </p>
        </div>

        {/* GitHub URL Input */}
        <div className="mb-5 space-y-2">
          <label className="block text-sm font-medium text-gray-400">GitHub Repository URL (Optional)</label>
          <Input
            type="text"
            placeholder="https://github.com/facebook/react"
            value={githubUrl}
            onChange={handleUrlChange}
          />
          <p className="text-xs text-gray-500">Paste a URL here to auto-fill the Owner and Repository fields below.</p>
        </div>

        {/* Row 1: Owner + Repo */}
        <div className="grid grid-cols-2 gap-6 mb-5">
          <div className="space-y-2">
            <label className="block text-sm font-medium text-gray-400">GitHub Owner</label>
            <Input
              type="text"
              placeholder="e.g. facebook"
              value={githubInfo.owner}
              onChange={set('owner')}
            />
          </div>
          <div className="space-y-2">
            <label className="block text-sm font-medium text-gray-400">Repository</label>
            <Input
              type="text"
              placeholder="e.g. react"
              value={githubInfo.repo}
              onChange={set('repo')}
            />
          </div>
        </div>

        {/* Row 2: Token + Branch */}
        <div className="grid grid-cols-2 gap-6 mb-8">
          <div className="space-y-2">
            <label className="block text-sm font-medium text-gray-400 flex items-center gap-1.5">
              <Lock size={13} className="text-gray-500" />
              GitHub Token
              <span className="ml-1 text-xs text-gray-600 font-normal">(private repos)</span>
            </label>
            <Input
              type="password"
              placeholder="ghp_xxxxxxxxxxxx"
              value={githubInfo.token}
              onChange={set('token')}
            />
          </div>
          <div className="space-y-2">
            <label className="block text-sm font-medium text-gray-400 flex items-center gap-1.5">
              <GitBranch size={13} className="text-gray-500" />
              Branch
              <span className="ml-1 text-xs text-gray-600 font-normal">(default: main)</span>
            </label>
            <Input
              type="text"
              placeholder="main"
              value={githubInfo.branch}
              onChange={set('branch')}
            />
          </div>
        </div>

        <Button
          variant="primary"
          className="w-full py-4 text-lg"
          onClick={handleStart}
          disabled={loading || !githubInfo.owner || !githubInfo.repo}
          icon={loading ? RefreshCw : Plus}
        >
          {loading ? 'Initializing...' : 'Initialize Deployment Agent'}
        </Button>
      </Card>
    </div>
  );
};

export default WelcomePage;
