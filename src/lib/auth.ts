import type { NextAuthOptions } from "next-auth";
import GitHubProvider from "next-auth/providers/github";
// Future providers — uncomment and add env vars when ready:
// import GoogleProvider from "next-auth/providers/google";
// import AzureADProvider from "next-auth/providers/azure-ad";

const githubAuthEnabled = Boolean(process.env.GITHUB_ID && process.env.GITHUB_SECRET);

export const authOptions: NextAuthOptions = {
    // TODO(remove after development): local fallback so the UI can boot before real auth env vars are documented.
    secret: process.env.NEXTAUTH_SECRET || (process.env.NODE_ENV !== "production" ? "dev-only-nextauth-secret-remove-later" : undefined),
    providers: githubAuthEnabled ? [
        GitHubProvider({
            clientId: process.env.GITHUB_ID!,
            clientSecret: process.env.GITHUB_SECRET!,
        }),
        // GoogleProvider({
        //     clientId: process.env.GOOGLE_CLIENT_ID!,
        //     clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
        // }),
        // AzureADProvider({
        //     clientId: process.env.AZURE_AD_CLIENT_ID!,
        //     clientSecret: process.env.AZURE_AD_CLIENT_SECRET!,
        //     tenantId: process.env.AZURE_AD_TENANT_ID,
        // }),
    ] : [],
    pages: {
        signIn: "/login",
    },
    callbacks: {
        jwt({ token, user }) {
            // Persist the user id into the JWT on first sign-in
            if (user) token.userId = user.id;
            return token;
        },
        session({ session, token }) {
            // Expose userId on the session so components can read it
            if (session.user) (session.user as any).id = token.userId ?? token.sub;
            return session;
        },
    },
};
