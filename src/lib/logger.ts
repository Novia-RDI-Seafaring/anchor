// Frontend Logger
// Structured logging utility for client-side logging

type LogLevel = 'info' | 'warn' | 'error' | 'debug';

interface LogMetadata {
    [key: string]: unknown;
}

class Logger {
    private isDevelopment = process.env.NODE_ENV !== 'production';

    private log(level: LogLevel, message: string, meta?: LogMetadata) {
        const timestamp = new Date().toISOString();
        const logEntry = {
            timestamp,
            level,
            message,
            ...meta,
        };

        // Console logging
        switch (level) {
            case 'error':
                console.error(`[${timestamp}] ERROR:`, message, meta || '');
                break;
            case 'warn':
                console.warn(`[${timestamp}] WARN:`, message, meta || '');
                break;
            case 'debug':
                if (this.isDevelopment) {
                    console.debug(`[${timestamp}] DEBUG:`, message, meta || '');
                }
                break;
            default:
                console.log(`[${timestamp}] INFO:`, message, meta || '');
        }

        // In production,  you could send to a service like Sentry, LogRocket, etc.
        if (!this.isDevelopment && level === 'error') {
            this.sendToErrorTracking(logEntry);
        }
    }

    info(message: string, meta?: LogMetadata) {
        this.log('info', message, meta);
    }

    warn(message: string, meta?: LogMetadata) {
        this.log('warn', message, meta);
    }

    error(message: string, error?: Error | unknown, meta?: LogMetadata) {
        const errorMeta = {
            ...meta,
            error: error instanceof Error ? {
                name: error.name,
                message: error.message,
                stack: error.stack,
            } : error,
        };
        this.log('error', message, errorMeta);
    }

    debug(message: string, meta?: LogMetadata) {
        this.log('debug', message, meta);
    }

    // User action tracking
    trackAction(action: string, meta?: LogMetadata) {
        this.log('info', `User Action: ${action}`, { ...meta, type: 'user_action' });
    }

    // API call tracking
    trackAPI(endpoint: string, method: string, duration?: number, meta?: LogMetadata) {
        this.log('info', `API Call: ${method} ${endpoint}`, {
            ...meta,
            type: 'api_call',
            endpoint,
            method,
            duration,
        });
    }

    private sendToErrorTracking(logEntry: object) {
        // TODO: Integrate with error tracking service
        // Example: Sentry.captureException(logEntry);
        console.log('Would send to error tracking:', logEntry);
    }
}

// Export singleton instance
export const logger = new Logger();
