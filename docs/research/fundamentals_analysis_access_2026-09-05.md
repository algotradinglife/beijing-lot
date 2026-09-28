# 分析页访问诊断（2026-09-05）

任务：#407。本次仅诊断页面访问，没有放行下游任务或完成摸底验收。

## Nowscore

历史页面：https://live.nowscore.com/analysis/1870517cn.html
当前候选：https://live.nowscore.com/analysis/3000054cn.html

历史页面在 curl HTTP/2、curl HTTP/1.1 和 Python requests 下均成功取得 HTTP 200、207924 bytes。标题为“2020年06月23日足球让球分析：埃克塞特城 VS 科切斯特联”，含积分、交锋、阵容文字。

同一历史链接的 requests 请求头对照：
- User-Agent: Mozilla/5.0，无 Referer：连接重置。
- 相同简短 UA，加 Referer https://www.nowscore.com/：200。
- 完整浏览器 UA，无 Referer：200。
- 完整浏览器 UA，加上述 Referer：200。

当前候选在最简 UA、无 Referer 下也被重置。本轮尚未对当前候选完成成功页面验证。

结论：不是历史链接失效、不是仅支持 HTTP/2，也不是 requests 本身无法访问。观察支持请求头相关的访问过滤，但没有站点规则证据，不能断言唯一触发因素；真实来源页 Referer 与完整客户端请求头应进入后续适配验证。之前笼统归为连接问题的判断已细化。

## Titan

历史候选：https://zq.titan007.com/analysis/1870517cn.htm
当前候选：https://zq.titan007.com/analysis/3000054cn.htm
主页：https://zq.titan007.com/
主页声明的跳转：https://zq.titan007.com/info/index_cn.htm

DNS、TCP、TLS 成功，证书校验通过。主页返回301，指向上述 info 页面。
两条分析页 HTTP/1.1 返回442、空正文；历史分析页 HTTP/2 报 PROTOCOL_ERROR。
info 页面 HTTP/1.1 返回442，35字节正文，以 GB18030 解码明确为：
“非法访问，您的行为已被WAF系统记录！”

结论：已取得 WAF 拦截的明确证据，不能把442当成比赛不存在。具体规则是出口IP、请求头、浏览器会话还是其他因素，尚未证实。取得明确拦截提示后没有继续尝试绕过。

Titan 同号仅为候选，跨站比赛身份尚未核实。用户人工打开后可确认是否同场、是否显示验证或上述拦截提示。

## 证据

原始诊断文件保存于 data/derived/fundamentals_census/20260905_http_diagnostic/。其中 results.json 是第一组四请求传输诊断；compare.py 与响应文件记录客户端对照。额外请求头对照结果见本文。没有拟合、特征准入或结算修改。
