import {
    CopilotRuntime,
    ExperimentalEmptyAdapter,
    copilotRuntimeNextJSAppRouterEndpoint,
} from "@copilotkit/runtime";
import { HttpAgent } from "@ag-ui/client";
import { NextRequest } from "next/server";

const serviceAdapter = new ExperimentalEmptyAdapter();

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001";

export const POST = async (req: NextRequest) => {
    const searchParams = req.nextUrl.searchParams;
    const model = searchParams.get("model");

    const url = model
        ? `${backendUrl}/agent?model=${encodeURIComponent(model)}`
        : `${backendUrl}/agent`;

    const payload = await req.json();
    const mergedPayload = {
        ...payload,
        body: {
            ...(payload?.body ?? {}),
            forwardedProps: {
                ...(payload?.body?.forwardedProps ?? {}),
                model: model ?? payload?.body?.forwardedProps?.model ?? "gpt-4o-mini",
            },
        },
    };

    const runtime = new CopilotRuntime({
        agents: {
            my_agent: new HttpAgent({
                url: url,
            }),
        } as any,
    });

    const { handleRequest } = copilotRuntimeNextJSAppRouterEndpoint({
        runtime,
        serviceAdapter,
        endpoint: "/api/copilotkit",
    });

    const headers = new Headers(req.headers);
    headers.set("content-type", "application/json");

    const rewrittenReq = new Request(req.url, {
        method: req.method,
        headers,
        body: JSON.stringify(mergedPayload),
    });

    return handleRequest(rewrittenReq as any);
};
