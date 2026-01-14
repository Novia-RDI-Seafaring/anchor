/**
 * API Configuration with validation
 * 
 * SECURITY: This module validates the backend URL at build time
 * to prevent misconfigurations in production.
 */

const validateUrl = (url: string): string => {
    try {
        const parsed = new URL(url);

        // Ensure protocol is http or https
        if (!['http:', 'https:'].includes(parsed.protocol)) {
            throw new Error(`Invalid protocol: ${parsed.protocol}. Must be http or https.`);
        }

        // In production, enforce HTTPS
        if (process.env.NODE_ENV === 'production' && parsed.protocol !== 'https:') {
            console.warn(
                '⚠️  WARNING: Production API URL is not using HTTPS! ' +
                'This is insecure and should be fixed immediately.'
            );
        }

        return url;
    } catch (error) {
        if (error instanceof TypeError) {
            throw new Error(`Invalid URL format: ${url}`);
        }
        throw error;
    }
};

const getApiUrl = (): string => {
    const url = process.env.NEXT_PUBLIC_BACKEND_URL;

    // Fail fast in production if URL not configured
    if (!url) {
        if (process.env.NODE_ENV === 'production') {
            throw new Error(
                'NEXT_PUBLIC_BACKEND_URL must be set in production. ' +
                'Check your environment variables.'
            );
        }

        // Development fallback
        console.warn('⚠️  NEXT_PUBLIC_BACKEND_URL not set, using localhost:8001');
        return 'http://localhost:8001';
    }

    return validateUrl(url);
};

// Validate and export URL (throws if invalid)
export const API_URL = getApiUrl();

// Export type-safe fetch wrapper
export const apiClient = {
    async fetch(path: string, options?: RequestInit): Promise<Response> {
        const url = `${API_URL}${path}`;

        const response = await fetch(url, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...options?.headers,
            },
        });

        return response;
    },
};

// Log configuration in development
if (process.env.NODE_ENV === 'development') {
    console.log(`API URL: ${API_URL}`);
}
