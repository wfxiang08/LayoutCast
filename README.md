# LayoutCast
是什么东西，工作原理见最后面！

## 1. 特色
* Fast cast code and resource changes, usually less than 5 sec.
	* `快速处理代码和Resource的变化，5s内生效`
* Cast does not reset your application. The running activity stack will be kept.
	* `保留当前的Activity Stack`, 一般情况下只更新当前的Activity
* Easy to setup, only add few lines of code.
	* `容易使用`
* Support both eclipse and AndroidStudio project.
	* `其实基本和IDE无关`，只是用到了IDE的某个目录结构的特点
* Provide a AndroidStudio plugin to click and cast.
	* 要求 `adb devices` 只有一个设备, 否则plugin就傻了，不过也不影响开发


## 2. 如何和Android Studio集成呢?

* 安装插件(安装一次就OK)
	1. Download Android Studio / Intellij plugin <https://github.com/mmin18/LayoutCast/raw/master/ide/IDEAPlugin/IDEAPlugin.jar>
	2. In Android Studio, go to `Preferences` > `Plugins` > `Install plugin from disk...`
	3. Choose the downloaded file from step #1 to install the plugin.
		* After restart, you should find a button at right of the run section: 
		* ![TOOLBAR](images/sc_toolbar.png)

* Android Project & Build System Changes
	* 添加依赖
```gradle
	dependencies {
		compile 'com.github.mmin18.layoutcast:library:1.+@aar'
		...
	}
```

	* 修改Application的代码
```java
public class MyApplication extends Application {
    @Override
    public void onCreate() {
        super.onCreate();

		// 只在测试时有效
        if (BuildConfig.DEBUG) {
            LayoutCast.init(this);
        }
    }
}
```
	* 修改AndroidManifest.xml
```xml
    <application
        android:name=".MyApplication"
		...

	<activity android:name="com.github.mmin18.layoutcast.ResetActivity" />
    <uses-permission android:name="android.permission.INTERNET" />
```

* 运行
	* 正常运行Android项目
	* 修改资源或者Java代码, 然后: `./cast.py` 或点击: Android Studio`工具栏上的按钮`
```bash
	cd <project path> 或项目root目录
	python cast.py
    python cast.py --device=xxxx

	Or you can specify the path in args:
	python cast.py <project path>
```




## Troubleshootings(一定要看)
* `这只是一个工具，保证能用，但是不保证任何场合都能用`（理论上OK, 但是没有经过完整测试）
* 目录结构的约定:
	* It can only find `/src` folder under `<project>/src` or `<project>/src/main/java`
	* It can only find `/res` folder under `<project>/res` or `<project>/src/main/res`
* 可以添加和修改资源，但是不能删除
	* You can add or replace resources, but you can't delete or rename resources (for now)
	* 删除之后重新使用gradle`编译运行即可`, 也就是放弃gradle的状态
* 异常如何处理:
	* If cast failed, clean your project, remove `/bin` and `/build` and rebuild again may solve the problem

-----

## How it Works

When **LayoutCast.init(context);** called, the application will start tiny http server in the background, and receive certain commands. Later on, the cast script running on your computer will communicate with your running app which is running through ADB TCP forward.

When the cast script runs, it will scan all possible ports on your phone to find the running LayoutCast server, and get the running application's resource list with its id, then compiled to `public.xml`. In which, it will be used later to keep resource id index consistent with the running application.

The cast script scans your project folder to find the `/res` folder, and all dependencies inside `/res` folder. You can run the **aapt** command to package all resources into **res.zip**, and then upload the zip file to the LayoutCast server to replace the resources of the running process. Then, it calls the **Activity.recreate()** to restart the visible activity.

Usually the activity will keep its running state in **onSaveInstanceState()** and restore after coming back later.



`Android SDK sucks. It's so slow to build and run which waste me a lot of time every day.`

## Motivation

Facebook Buck <http://github.com/facebook/buck> build is fast. However, the biggest problem with Buck is, it requires you to change a lot of codes, and restructs your project in small modules. Indeed, it is troublesome to just make it work properly on the existing android project, especially if you have big project. I have tried using Buck build system instead of Gradle on my test project. However, it took me a week just to make it work.

What I needs is a build tool that is easy to setup, fast as Buck, and provide a Run button in Android Studio. So I created LayoutCast.

**LayoutCast** is a little tool to help with that, it will cast every changes in your Java source code or resources (including library project) to your phone or emulator within 5 sec, and does not restart your application.

把代码和资源文件的改动直接同步到手机上，应用不需要重启。省去了编译运行漫长的等待，比较适合真机调试的时候使用。

![GIF](images/cast_res.gif)
![GIF](images/cast_code.gif)

Youtube demo video: <https://youtu.be/rc04LK2_suU>

优酷: <http://v.youku.com/v_show/id_XMTMwNTUzOTQ3Mg>


## Limitations

- ~~LayoutCast only support Mac (for now)~~
- Cast Java code only support ART runtime (Android 5.0)

## Benchmarks

Here is how it compared to Gradle and Facebook Buck:

![BENCHMARK](images/benchmark1.png)

The test machine is a 2015 MBP with a 2014 MotoX.

The test project's apk is about 14.3MB, which contains 380k lines of java code and 86k lines of xml files.


