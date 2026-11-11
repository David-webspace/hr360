import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// 只做「有沒有 cookie」的樂觀檢查；真正的身分驗證在後端每個 API
export function proxy(request: NextRequest) {
  if (!request.cookies.has("hr360_session")) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!login|api|_next|favicon.ico).*)"],
};
