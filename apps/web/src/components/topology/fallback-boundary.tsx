"use client";

import { Component, type ReactNode } from "react";

/** Renders `fallback` and reports once if the 3D view throws (shader, driver, or WebGL errors). */
export class FallbackBoundary extends Component<
  { fallback: ReactNode; onError: () => void; children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch() {
    this.props.onError();
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}
