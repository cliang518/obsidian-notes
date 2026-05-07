# CAD 图纸接入方案

## 当前选型

- `DXF` 直读：后端使用 `ezdxf`
- `DWG` 预留转换：优先接 `ODA File Converter`
- `LibreDWG` 作为后续研究备选，不作为当前主链路

## 当前已经支持

- 上传 `DXF` / `DWG`
- 记录图纸台账
- 解析 `DXF` 中的文本锚点
- 自动识别 `10.0.xx` 形式的 IP 尾号提示
- 根据 V2 现有摄像头、区域、平台来源，给出候选摄像头匹配

## 当前限制

- `DWG` 还未在运行机上直接完成自动转换
- 当前先做文本锚点识别，还没做完整矢量渲染
- 图纸中的 `10.0.xx` 只是 IP 尾号锚点，最终匹配仍需结合楼层、区域、平台来源交叉校验

## 推荐提供格式

1. `DXF`
2. `DWG`
3. `PDF`
4. 高清导出图片

## 推荐资料

- 图纸文件
- 楼层名
- 区域名
- 已知几个摄像头完整 IP
- 如果图纸里有 `10.0.xx` 文本，说明它是否等于真实 IP 后两位

## 后续扩展方向

- 图纸矢量渲染
- 点位人工校正
- 图纸与区域地图联动
- 动态告警高亮
- 交换机 / 摄像头 / 控制点位统一空间拓扑

## 参考

- ezdxf: https://ezdxf.readthedocs.io/
- ODA File Converter: https://www.opendesign.com/guestfiles/oda_file_converter
- LibreDWG: https://www.gnu.org/software/libredwg/
