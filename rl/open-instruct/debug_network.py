import asyncio
import os
import httpx
import time

# 1. 强制设置环境变量（确保和你 curl 成功时的一致）
PROXY_URL = "http://httpproxy.glm.ai:8888"
os.environ["HTTP_PROXY"] = PROXY_URL
os.environ["HTTPS_PROXY"] = PROXY_URL
os.environ["ALL_PROXY"] = PROXY_URL

# OpenRouter 目标
TARGET_URL = "https://openrouter.ai/api/v1/models"

async def test_request(use_http2, trust_env=True, name="测试"):
    print(f"\n--- {name} [HTTP/2={use_http2}] ---")
    start = time.time()
    try:
        async with httpx.AsyncClient(
            http2=use_http2,  # 关键开关
            trust_env=trust_env, # 是否读取环境变量代理
            verify=False,    # 临时关闭SSL验证排除证书问题
            timeout=10.0
        ) as client:
            print(f"正在发送请求到 {TARGET_URL} ...")
            resp = await client.get(TARGET_URL)
            print(f"✅ 状态码: {resp.status_code}")
            print(f"✅ 协议版本: {resp.http_version}")
            print(f"⏱️ 耗时: {time.time() - start:.2f}s")
            return True
    except Exception as e:
        print(f"❌ 失败: {type(e).__name__} - {e}")
        print(f"⏱️ 耗时: {time.time() - start:.2f}s")
        return False

async def main():
    print(f"当前代理配置: {PROXY_URL}")
    
    # 测试 A: 默认行为 (开启 HTTP/2) -> LiteLLM 的默认模式
    print("\n[A] 模拟 LiteLLM 默认行为 (HTTP/2 开启)")
    success_a = await test_request(use_http2=True, name="默认(HTTP/2)")
    
    # 测试 B: 强制降级到 HTTP/1.1 -> Curl 的行为
    print("\n[B] 模拟 Curl 行为 (强制 HTTP/1.1)")
    success_b = await test_request(use_http2=False, name="降级(HTTP/1.1)")

    print("\n" + "="*30)
    print("结论分析:")
    if not success_a and success_b:
        print("🔴 你的代理服务器不支持 HTTP/2！这正是 LiteLLM 失败的原因。")
        print("解决方案：必须强制 LiteLLM/httpx 使用 HTTP/1.1。")
    elif not success_a and not success_b:
        print("🔴 代理或网络完全不可达。检查 IP 白名单或防火墙。")
    elif success_a:
        print("🟢 HTTP/2 竟然通了？那可能是 LiteLLM 的客户端复用逻辑有问题。")

if __name__ == "__main__":
    asyncio.run(main())