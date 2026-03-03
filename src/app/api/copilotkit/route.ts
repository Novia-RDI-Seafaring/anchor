import {
    CopilotRuntime,
    ExperimentalEmptyAdapter,
    copilotRuntimeNextJSAppRouterEndpoint,
} from "@copilotkit/runtime";
import { HttpAgent } from "@ag-ui/client";
import { NextRequest } from "next/server";

// 1. You can use any service adapter here for multi-agent support. We use
//    the empty adapter since we're only using one agent.
const serviceAdapter = new ExperimentalEmptyAdapter();

// 2. Create the CopilotRuntime instance and utilize the PydanticAI AG-UI
//    integration to setup the connection.
const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001";
const backendUrl2 = process.env.NEXT_PUBLIC_BACKEND_URL_2 || "http://localhost:8080";

// 3. Build a Next.js API route that handles the CopilotKit runtime requests.
export const POST = async (req: NextRequest) => {
    // Extract model from query params
    const searchParams = req.nextUrl.searchParams;
    const model = searchParams.get("model");

    // Create a per-request runtime (or just agent) to include the model param
    // CopilotRuntime is lightweight enough to create per request if needed for config,
    // or we can just pass the url with param.
    // NOTE: HttpAgent from @ag-ui/client might be reusable but the URL needs to be dynamic.

    const url = model
        ? `${backendUrl}/agent?model=${encodeURIComponent(model)}`
        : `${backendUrl}/agent`;


    const ketju_url = `${backendUrl2}/agent`



    // Merge model into body payload while preserving all existing fields.
    const payload = await req.json();
    console.log(payload);
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
    console.log(mergedPayload);

    const runtime = new CopilotRuntime({
        agents: {
            my_agent: new HttpAgent({
                url: url,
            }),
        } as any,  // Type cast for compatibility with CopilotKit 1.50
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
