# shanbay2anki

一款可以从扇贝阅读导入生词本的 Anki 的插件。

本项目主体架构和大量代码都基于 [Dict2Anki](https://github.com/megachweng/Dict2Anki)。

使用方法：

![Usage](https://user-images.githubusercontent.com/16643669/84895102-6f97dc00-b0d4-11ea-820c-aa251570bdac.gif)

生成的单词书在 AnkiDroid 上的使用效果：

![AnkiDroid](https://user-images.githubusercontent.com/16643669/84896786-1ed5b280-b0d7-11ea-85d4-c95059e9efe9.gif)

## 安装

Anki --> 工具 --> 附加组件 --> 获取插件  

插件代码：775172794


## 目前存在的问题

* 同步更新功能暂时还没有做，每次创建单词书的时候请选择一个新的牌组。
* 如果想要跳转到单词在书中所在的位置，需要安装[Xposed 模块](https://github.com/bet4it/IntentAnywhere/releases/tag/v1.0)。
* 由于一些特殊原因，不公开获取原句翻译的代码。