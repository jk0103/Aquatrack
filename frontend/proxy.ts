import { NextRequest, NextResponse } from "next/server";

// Must match COOKIE_NAME in src/aquatrack/api/auth.py
const SESSION_COOKIE = "aquatrack_session";

// Optimistic check only: sends visitors without a session cookie to the login page.
// The API still verifies the cookie on every request.
export default function proxy(req: NextRequest) {
  if (!req.cookies.has(SESSION_COOKIE)) {
    return NextResponse.redirect(new URL("/login", req.nextUrl));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/"],
};
