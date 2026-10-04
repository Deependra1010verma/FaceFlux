/**
 * motion-shim.tsx — CSS-transition fallback for framer-motion.
 *
 * Provides the same import API as framer-motion so components compile
 * without the package installed. When framer-motion is installed via
 * `npm install`, switch imports back to "framer-motion".
 *
 * After install: sed -i 's|@/lib/motion-shim|framer-motion|g' \
 *   components/*.tsx app/page.tsx
 */

"use client";

import React, { CSSProperties, ComponentPropsWithRef } from "react";

// ── Shared motion prop types ───────────────────────────────────────────────────
export type MotionValue = string | number | boolean | (string | number)[] | undefined;
export type MotionStyle = Record<string, MotionValue>;

export interface MotionProps {
  animate?: MotionStyle;
  initial?: MotionStyle | boolean;
  exit?: MotionStyle;
  whileHover?: MotionStyle;
  whileTap?: MotionStyle;
  transition?: Record<string, unknown>;
  layout?: boolean | string;
  layoutId?: string;
  key?: React.Key;
}

// Strip motion-specific props before passing to DOM
function stripMotion<T extends MotionProps>(props: T) {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { animate, initial, exit, whileHover, whileTap, transition, layout, layoutId, ...rest } = props;
  return rest;
}

// ── motion.div ────────────────────────────────────────────────────────────────
type DivProps = MotionProps & ComponentPropsWithRef<"div"> & { style?: CSSProperties };
const Div = React.forwardRef<HTMLDivElement, DivProps>((props, ref) => {
  const rest = stripMotion(props);
  return <div {...rest} ref={ref} style={{ transition: "all 0.2s ease", ...props.style }} />;
});
Div.displayName = "motion.div";

// ── motion.button ────────────────────────────────────────────────────────────
type ButtonProps = MotionProps & ComponentPropsWithRef<"button"> & { style?: CSSProperties };
const Button = React.forwardRef<HTMLButtonElement, ButtonProps>((props, ref) => {
  const rest = stripMotion(props);
  return <button {...rest} ref={ref} style={{ transition: "all 0.15s ease", ...props.style }} />;
});
Button.displayName = "motion.button";

// ── motion.a ─────────────────────────────────────────────────────────────────
type AnchorProps = MotionProps & ComponentPropsWithRef<"a"> & { style?: CSSProperties };
const Anchor = React.forwardRef<HTMLAnchorElement, AnchorProps>((props, ref) => {
  const rest = stripMotion(props);
  return <a {...rest} ref={ref} style={{ transition: "all 0.15s ease", ...props.style }} />;
});
Anchor.displayName = "motion.a";

// ── motion.span ───────────────────────────────────────────────────────────────
type SpanProps = MotionProps & ComponentPropsWithRef<"span"> & { style?: CSSProperties };
const Span = React.forwardRef<HTMLSpanElement, SpanProps>((props, ref) => {
  const rest = stripMotion(props);
  return <span {...rest} ref={ref} style={{ transition: "all 0.2s ease", ...props.style }} />;
});
Span.displayName = "motion.span";

// ── motion.section ────────────────────────────────────────────────────────────
type SectionProps = MotionProps & ComponentPropsWithRef<"section"> & { style?: CSSProperties };
const Section = React.forwardRef<HTMLElement, SectionProps>((props, ref) => {
  const rest = stripMotion(props);
  return <section {...rest} ref={ref as React.Ref<HTMLElement>} style={{ transition: "all 0.2s ease", ...props.style }} />;
});
Section.displayName = "motion.section";

// ── motion.p ─────────────────────────────────────────────────────────────────
type PProps = MotionProps & ComponentPropsWithRef<"p"> & { style?: CSSProperties };
const P = React.forwardRef<HTMLParagraphElement, PProps>((props, ref) => {
  const rest = stripMotion(props);
  return <p {...rest} ref={ref} style={{ transition: "all 0.2s ease", ...props.style }} />;
});
P.displayName = "motion.p";

// ── motion namespace ──────────────────────────────────────────────────────────
export const motion = { div: Div, button: Button, a: Anchor, span: Span, section: Section, p: P };

// ── AnimatePresence shim ──────────────────────────────────────────────────────
export function AnimatePresence({
  children,
}: {
  children?: React.ReactNode;
  mode?: "wait" | "sync" | "popLayout";
  initial?: boolean;
}) {
  return <>{children}</>;
}

// ── Hooks ─────────────────────────────────────────────────────────────────────
export function useReducedMotion(): boolean { return false; }
export function useAnimation() { return { start: () => {}, stop: () => {} }; }
