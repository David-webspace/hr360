// 瀏覽器只和 Next.js 同源溝通；這裡把 /api/* 轉給後端，登入 cookie 原樣往返
const BACKEND = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8360";

async function forward(request: Request, ctx: RouteContext<"/api/[...path]">) {
  const { path } = await ctx.params;
  const url = new URL(request.url);
  const target = `${BACKEND}/api/${path.map(encodeURIComponent).join("/")}${url.search}`;
  const headers = new Headers();
  for (const h of ["cookie", "content-type"]) {
    const v = request.headers.get(h);
    if (v) headers.set(h, v);
  }
  const res = await fetch(target, {
    method: request.method,
    headers,
    body: request.method === "GET" ? undefined : await request.arrayBuffer(), // 二進位安全：上傳圖片也走這裡
    cache: "no-store",
  });
  const out = new Headers({ "content-type": res.headers.get("content-type") ?? "application/json" });
  const cache = res.headers.get("cache-control");
  if (cache) out.set("cache-control", cache);
  for (const c of res.headers.getSetCookie()) out.append("set-cookie", c);
  return new Response(res.body, { status: res.status, headers: out });
}

export { forward as GET, forward as POST };
