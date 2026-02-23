import React, { useState } from 'react';
import { Terminal, Mail, Lock, LogIn, RefreshCw, UserPlus } from 'lucide-react';
import { api, setAuthToken } from './services/api';
import { authService } from './services/auth';

function Login({ onLogin }) {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      let data;
      if (isLogin) {
        data = await authService.signIn(email, password);
      } else {
        data = await authService.signUp(email, password);
      }

      const authData = {
        token: data.idToken,
        refreshToken: data.refreshToken,
        email: data.email,
        userId: data.localId,
        expiry: Date.now() + (parseInt(data.expiresIn) * 1000)
      };
      localStorage.setItem('tca_auth', JSON.stringify(authData));
      setAuthToken(data.idToken);
      // Sync user to MongoDB (non-blocking — login still succeeds if this fails)
      try { await api.syncUser(); } catch (e) { console.warn('User sync failed:', e); }
      onLogin(authData);
    } catch (err) {
      setError(err.response?.data?.error?.message || err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleSignIn = async () => {
    setGoogleLoading(true);
    setError('');
    try {
      const data = await authService.signInWithGoogle();
      const authData = {
        token: data.idToken,
        refreshToken: data.refreshToken,
        email: data.email,
        userId: data.localId,
        expiry: Date.now() + (parseInt(data.expiresIn) * 1000)
      };
      localStorage.setItem('tca_auth', JSON.stringify(authData));
      setAuthToken(data.idToken);
      // Sync user to MongoDB (non-blocking — login still succeeds if this fails)
      try { await api.syncUser(); } catch (e) { console.warn('User sync failed:', e); }
      onLogin(authData);
    } catch (err) {
      setError(err.message);
    } finally {
      setGoogleLoading(false);
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen p-8 bg-radial">
      <div className="card w-full max-w-md animate-fade-in">
        <div className="text-center mb-10">
          <div className="inline-flex p-4 rounded-2xl bg-primary-gradient mb-4">
            <Terminal size={40} className="text-white" />
          </div>
          <h1 className="text-2xl font-bold mb-2">Terraform Cloud Agent</h1>
          <p className="text-text-secondary">{isLogin ? 'Welcome back, sign in to continue' : 'Create an account to get started'}</p>
        </div>

        {/* Google Sign-In Button */}
        <button
          type="button"
          onClick={handleGoogleSignIn}
          disabled={googleLoading || loading}
          className="w-full flex items-center justify-center gap-3 py-3 px-4 rounded-xl border border-white/10 bg-white/5 hover:bg-white/10 transition-all font-medium mb-6 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {googleLoading ? (
            <RefreshCw size={18} className="animate-spin" />
          ) : (
            <svg width="18" height="18" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg">
              <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
              <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
              <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
              <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
              <path fill="none" d="M0 0h48v48H0z"/>
            </svg>
          )}
          Continue with Google
        </button>

        {/* Divider */}
        <div className="flex items-center gap-4 mb-6">
          <div className="flex-1 h-px bg-white/10"></div>
          <span className="text-xs text-text-muted">or continue with email</span>
          <div className="flex-1 h-px bg-white/10"></div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="space-y-4">
            <label className="block text-sm font-medium text-text-secondary">Email Address</label>
            <div className="relative">
              <Mail className="absolute left-4 top-3 text-text-muted" size={18} />
              <input
                type="email"
                required
                className="w-full bg-white/5 border border-white/10 rounded-xl p-3 pl-12 focus:outline-none focus:border-indigo-500 transition-all"
                placeholder="you@example.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
              />
            </div>
          </div>

          <div className="space-y-4">
            <label className="block text-sm font-medium text-text-secondary">Password</label>
            <div className="relative">
              <Lock className="absolute left-4 top-3 text-text-muted" size={18} />
              <input
                type="password"
                required
                className="w-full bg-white/5 border border-white/10 rounded-xl p-3 pl-12 focus:outline-none focus:border-indigo-500 transition-all"
                placeholder="••••••••"
                value={password}
                onChange={e => setPassword(e.target.value)}
              />
            </div>
          </div>

          {error && (
            <div className="p-3 rounded-lg bg-error-color/10 border border-error-color/20 text-error-color text-xs text-center">
              {error}
            </div>
          )}

          <button
            type="submit"
            className="btn btn-primary w-full py-3"
            disabled={loading || googleLoading}
          >
            {loading ? <RefreshCw className="animate-spin" /> : (
              <>{isLogin ? <LogIn size={18} /> : <UserPlus size={18} />} {isLogin ? 'Sign In' : 'Sign Up'}</>
            )}
          </button>
        </form>

        <div className="mt-8 text-center">
          <button
            className="text-sm text-text-muted hover:text-text-primary transition-all"
            onClick={() => setIsLogin(!isLogin)}
          >
            {isLogin ? "Don't have an account? Sign Up" : "Already have an account? Sign In"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default Login;
