import { SignInButton, UserButton } from "@clerk/react";
import { Authenticated, AuthLoading, Unauthenticated } from "convex/react";
import { Component, type ErrorInfo, type ReactNode } from "react";

import { LiveOperationsConsole } from "./LiveOperationsConsole";

class AuthorizationBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Operations console failed closed", error.name, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return <main className="auth-state"><h1>Access denied</h1><p>Your authenticated account is not authorized for clinic operations.</p></main>;
    }
    return this.props.children;
  }
}

export function App() {
  return <>
    <AuthLoading><main className="auth-state"><p>Authenticating…</p></main></AuthLoading>
    <Unauthenticated><main className="auth-state"><h1>Hermes Operations</h1><SignInButton mode="modal"><button className="primary">Sign in with Google Workspace</button></SignInButton></main></Unauthenticated>
    <Authenticated>
      <AuthorizationBoundary>
        <div className="operator-session"><UserButton /></div>
        <LiveOperationsConsole />
      </AuthorizationBoundary>
    </Authenticated>
  </>;
}
