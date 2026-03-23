import { NextResponse } from "next/server";
import { withAuth } from "next-auth/middleware";

const authEnabled = Boolean(process.env.GITHUB_ID && process.env.GITHUB_SECRET);

const authMiddleware = withAuth({
    pages: {
        signIn: "/login",
    },
});

export default authEnabled
    ? authMiddleware
    : function middleware() {
        // TODO(remove after development): bypass auth until real provider env vars are configured.
        return NextResponse.next();
    };

export const config = {
    // Protect everything except the auth endpoints, login page, and Next.js internals
    matcher: ["/((?!api/auth|login|_next/static|_next/image|favicon.ico).*)"],
};
