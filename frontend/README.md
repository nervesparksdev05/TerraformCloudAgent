# TerraformCloudAgent — Frontend

React + Vite frontend for the TerraformCloudAgent application.

## Stack

- **React 18** — UI framework
- **Vite** — Build tool and dev server
- **Firebase JS SDK** — Google OAuth and email/password authentication
- **Axios** — HTTP client for backend API calls
- **Lucide React** — Icon library

## Getting Started

```bash
npm install
npm run dev
# Runs at http://localhost:5174
```

## Environment

The frontend reads `VITE_API_BASE_URL` from `.env` (defaults to `http://localhost:8000`).

```env
VITE_API_BASE_URL=http://localhost:8000
```

## Structure

```
src/
├── pages/
│   ├── WelcomePage.jsx      # New chat form — GitHub owner, repo, token (private repos), branch
│   └── WorkspacePage.jsx    # Main workspace with three tabs:
│                            #   Conversation | File Review (edit) | Lifecycle
├── components/
│   ├── common/              # Button, Card, Input, Badge
│   ├── features/
│   │   └── chat/            # ChatPanel, ChatMessage, ChatInput
│   │                        # CodeViewer (read-only), CodeEditor (inline edit)
│   └── layout/              # Sidebar (session list, navigation)
├── services/
│   ├── client.js            # Axios instance + all API methods
│   ├── api.js               # Re-exports from client.js
│   ├── auth.js              # Firebase REST API + Google OAuth (signInWithPopup)
│   └── firebase.js          # Firebase app initialization
├── hooks/
│   ├── useAuth.js           # Auth state from localStorage
│   └── useSession.js        # Session/conversation state
├── App.jsx                  # Root component, routing between Login/Welcome/Workspace
└── Login.jsx                # Email/password + Google sign-in UI
```

## Key Features

- **Google Sign-In** via Firebase popup (`signInWithGoogle`)
- **Email/password** sign-up and sign-in
- **User sync** — calls `POST /auth/sync-user` after every login to persist user in MongoDB
- **Streaming chat** — uses `fetch` with SSE to stream bot responses token-by-token
- **Inline Terraform editing** — CodeEditor component with Edit/Save/Cancel per file
- **AI re-generation** — natural language feedback sent to `POST /runs/{id}/edit`
- **Private repo support** — GitHub token and branch fields on the new chat form

## Build

```bash
npm run build
# Output in dist/
```
