# Wan-TV

面向 APTV 的公开免费 IPTV 聚合播放列表，每天自动更新、整理并去重。

## APTV 固定订阅地址

```text
https://raw.githubusercontent.com/wanshushu1217-netizen/Wan-TV/main/Wan-TV.m3u
```

在 APTV 中新增远程 M3U 播放列表并粘贴上面的地址即可。仓库内文件会更新，但订阅 URL 不变。

## 数据来源与处理方式

本项目只聚合上游声明为公开可访问、免费使用的 IPTV 播放列表：

- [iptv-org/iptv](https://github.com/iptv-org/iptv)
- [Free-TV/IPTV](https://github.com/Free-TV/IPTV)

更新脚本会下载上游 M3U、过滤成人分类、按地区/语言/类型整理，并按频道 ID、名称和串流 URL 去重。Free-TV 条目拥有较高优先级。

> 频道可用性、地区限制和版权状态可能随时间变化。本仓库不托管视频，仅整理上游公开链接。

## 自动更新

GitHub Actions 每天约在台北时间 12:17（UTC 04:17）运行，也可在 Actions 页面手动执行。只有播放列表内容变化时才提交更新。

## 文件

- `Wan-TV.m3u`：APTV 使用的最终播放列表
- `scripts/update_playlist.py`：下载、过滤、整理和去重脚本
- `.github/workflows/update-playlist.yml`：每日自动更新工作流
