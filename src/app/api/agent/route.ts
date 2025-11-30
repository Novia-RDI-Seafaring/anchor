// import { HttpAgent } from "@ag-ui/client";
// import { NextRequest, NextResponse } from "next/server";

// AG-UI runtime endpoint for Pydantic AI backend (mounted at /agent)
//const agentUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001";
//const agentEndpoint = `${agentUrl}/agent`;

//export const POST = async (req: NextRequest) => {
//    try {
//        const body = await req.json();

//        // Forward request to Pydantic AI backend
//        const response = await fetch(agentEndpoint, {
//            method: 'POST',
//            headers: {
//                'Content-Type': 'application/json',
//            },
//            body: JSON.stringify(body),
//        });

//        if (!response.ok) {
//            throw new Error(`Backend responded with status: ${response.status}`);
//        }

//        const data = await response.json();
//        return NextResponse.json(data);

//    } catch (error) {
//        console.error('Error communicating with Pydantic AI backend:', error);
//        return NextResponse.json(
//            { error: 'Failed to communicate with backend' },
//            { status: 500 }
//        );
//    }
//};
