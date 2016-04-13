package com.github.mmin18.layoutcast.server;

import android.app.Application;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.content.res.Resources;
import android.util.Log;

import com.github.mmin18.layoutcast.LayoutCast;
import com.github.mmin18.layoutcast.context.OverrideContext;
import com.github.mmin18.layoutcast.util.EmbedHttpServer;
import com.github.mmin18.layoutcast.util.ResUtils;

import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.security.MessageDigest;
import java.util.HashMap;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;

/**
 * GET /packagename (get the application package name)<br>
 * POST /pushres (upload resources file)<br>
 * PUT /pushres (upload resources file)<br>
 * POST /lcast (cast to all activities)<br>
 * POST /reset (reset all activities)<br>
 * GET /ids.xml<br>
 * GET /public.xml<br>
 *
 * @author mmin18
 */
public class LcastServer extends EmbedHttpServer {
    public static final int PORT_FROM = 41128;
    public static Application app;
    final Context context;

    File latestPushResFile; // 最新的资源文件

    private LcastServer(Context ctx, int port) {
        super(port);
        context = ctx;
    }

    @Override
    protected void handle(String method, String path,
                          HashMap<String, String> headers, InputStream input,
                          ResponseOutputStream response) throws Exception {
        // 1. 获取Context的pacakgename
        if (path.equalsIgnoreCase("/packagename")) {
            response.setContentTypeText();
            // 范围当前Context的PackageName
            response.write(context.getPackageName().getBytes("utf-8"));
            return;
        }

        // 2. 获取App State: 2 表示正常前台运行, 只有处于前台运行的程序才能修改代码和资源
        if (path.equalsIgnoreCase("/appstate")) {
            response.setContentTypeText();
            response.write(String.valueOf(OverrideContext.getApplicationState()).getBytes("utf-8"));
            return;
        }

        // 2. 获取vm版本: 2.xx 表示支持 ART
        //    http://stackoverflow.com/questions/19830342/how-can-i-detect-the-android-runtime-dalvik-or-art
        //    https://source.android.com/devices/tech/dalvik/
        if ("/vmversion".equalsIgnoreCase(path)) {
            final String vmVersion = System.getProperty("java.vm.version");
            response.setContentTypeText();
            if (vmVersion == null) {
                response.write('0');
            } else {
                response.write(vmVersion.getBytes("utf-8"));
            }
            return;
        }

        // 3. 获取:
        if ("/launcher".equalsIgnoreCase(path)) {
            PackageManager pm = app.getPackageManager();

            //
            Intent i = new Intent(Intent.ACTION_MAIN);
            i.addCategory(Intent.CATEGORY_LAUNCHER);
            i.setPackage(app.getPackageName());
            ResolveInfo ri = pm.resolveActivity(i, 0);

//            i = new Intent(Intent.ACTION_MAIN);
//            i.addCategory(Intent.CATEGORY_LAUNCHER);

            // 获取launcher的界面
            response.setContentTypeText();
            response.write(ri.activityInfo.name.getBytes("utf-8"));
            return;
        }

        // pushres 如何处理呢?
        if (("post".equalsIgnoreCase(method) || "put".equalsIgnoreCase(method)) && path.equalsIgnoreCase("/pushres")) {
            File dir = new File(context.getCacheDir(), "lcast");
            dir.mkdir();

            // lcast/
            //      dex.ped
            //      res.ped
            //      xxxx.apk
            File dex = new File(dir, "dex.ped");

            // 如果存在: dex.ped, 那么采用: res.ped, 否则采用: apk(什么逻辑呢?)
            File file;
            if (dex.length() > 0) {
                file = new File(dir, "res.ped");
            } else {
                file = new File(dir, Integer.toHexString((int) (System.currentTimeMillis() / 100) & 0xfff) + ".apk");
            }

            // 通过Http Post发送什么信息呢?
            // dex.ped
            // *.apk
            FileOutputStream fos = new FileOutputStream(file);
            byte[] buf = new byte[4096];
            int l;
            while ((l = input.read(buf)) != -1) {
                fos.write(buf, 0, l);
            }
            fos.close();
            latestPushResFile = file;
            response.setStatusCode(201);
            Log.d("lcast", "lcast resources file received (" + file.length() + " bytes): " + file);
            return;
        }


        if (("post".equalsIgnoreCase(method) || "put".equalsIgnoreCase(method)) && path.equalsIgnoreCase("/pushdex")) {
            File dir = new File(context.getCacheDir(), "lcast");
            dir.mkdir();

            // lcast/
            //       dex.ped
            //
            File file = new File(dir, "dex.ped");
            FileOutputStream fos = new FileOutputStream(file);
            byte[] buf = new byte[4096];
            int l;
            while ((l = input.read(buf)) != -1) {
                fos.write(buf, 0, l);
            }
            fos.close();
            response.setStatusCode(201);
            Log.d("lcast", "lcast dex file received (" + file.length() + " bytes)");
            return;
        }

        // 如何重启呢?
        if ("/pcast".equalsIgnoreCase(path)) {
            // 告知用户要重启(注意参数: false)
            // 用户可以选择关闭
            LayoutCast.restart(false);
            response.setStatusCode(200);
            return;
        }

        /**
         * dex.ped  res.ped 之间的关系
         * 1. 启动前, 如果dex.ped存在，变成: dex.apk, 然后通过class loader加载；res.apk等文件要被删除
         * 2. 如果res.ped存在，则变成: res.apk 进行加载
         * 3. 上传资源时如果: dex.ped存在，则以 res.ped保存；说明接下来马上就要重启，dex.ped加载之后，再加载: res.ped
         * 4. 如果dex.ped不存在，则直接保存为 res.apk
         */
        if ("/lcast".equalsIgnoreCase(path)) {
            File dir = new File(context.getCacheDir(), "lcast");
            File dex = new File(dir, "dex.ped");

            // 1. 如果存在: dex 文件, 则将: latestPushResFile 修改为: res.ped; 然后重启
            if (dex.length() > 0) {
                // 代码修改了，临时修改: latestPushResFile, 然后重启代码， 防止: res.ped被删除
                if (latestPushResFile != null) {
                    File f = new File(dir, "res.ped");
                    latestPushResFile.renameTo(f);
                }
                Log.i("lcast", "cast with dex changes, need to restart the process (activity stack will be reserved)");
                boolean b = LayoutCast.restart(true);
                response.setStatusCode(b ? 200 : 500);
            } else {

                // 没有代码的修改
                Resources res = ResUtils.getResources(app, latestPushResFile);
                OverrideContext.setGlobalResources(res);

                response.setStatusCode(200);
                response.write(String.valueOf(latestPushResFile).getBytes("utf-8"));
                Log.i("lcast", "cast with only res changes, just recreate the running activity.");
            }
            return;
        }

        // 资源恢复默认的资源
        if ("/reset".equalsIgnoreCase(path)) {
            OverrideContext.setGlobalResources(null);
            response.setStatusCode(200);
            response.write("OK".getBytes("utf-8"));
            return;
        }

        // 读取: 最终apk的资源
        //      例如: me.chunyu.ChunyuYuer.R (由于Android的Resource Union, 它基本上包含多有的id信息)
        if ("/ids.xml".equalsIgnoreCase(path)) {
            String Rn = app.getPackageName() + ".R";

            Class<?> Rclazz = app.getClassLoader().loadClass(Rn);
            String str = new IdProfileBuilder(context.getResources()).buildIds(Rclazz);

            response.setStatusCode(200);
            response.setContentTypeText();
            response.write(str.getBytes("utf-8"));
            return;
        }

        if ("/public.xml".equalsIgnoreCase(path)) {
            String Rn = app.getPackageName() + ".R";
            Class<?> Rclazz = app.getClassLoader().loadClass(Rn);
            String str = new IdProfileBuilder(context.getResources()).buildPublic(Rclazz);
            response.setStatusCode(200);
            response.setContentTypeText();
            response.write(str.getBytes("utf-8"));
            return;
        }

        if ("/apkinfo".equalsIgnoreCase(path)) {
            ApplicationInfo ai = app.getApplicationInfo();
            File apkFile = new File(ai.sourceDir);
            // 获取Apk的信息:
            //      size, lastModified, md5
            JSONObject result = new JSONObject();
            result.put("size", apkFile.length());
            result.put("lastModified", apkFile.lastModified());

            FileInputStream fis = new FileInputStream(apkFile);
            MessageDigest md5 = MessageDigest.getInstance("MD5");
            byte[] buf = new byte[4096];
            int l;
            while ((l = fis.read(buf)) != -1) {
                md5.update(buf, 0, l);
            }
            fis.close();

            result.put("md5", byteArrayToHex(md5.digest()));
            response.setStatusCode(200);
            response.setContentTypeJson();
            response.write(result.toString().getBytes("utf-8"));
            return;
        }

        // 获取原始的apk数据
        if ("/apkraw".equalsIgnoreCase(path)) {
            ApplicationInfo ai = app.getApplicationInfo();

            // 将apk直接下载下来
            FileInputStream fis = new FileInputStream(ai.sourceDir);
            response.setStatusCode(200);
            response.setContentTypeBinary();
            byte[] buf = new byte[4096];
            int l;
            while ((l = fis.read(buf)) != -1) {
                response.write(buf, 0, l);
            }
            return;
        }

        if (path.startsWith("/fileinfo/")) {
            ApplicationInfo ai = app.getApplicationInfo();
            File apkFile = new File(ai.sourceDir);

            JarFile jarFile = new JarFile(apkFile);
            // 获取其中的fileinfo
            JarEntry je = jarFile.getJarEntry(path.substring("/fileinfo/".length()));
            InputStream ins = jarFile.getInputStream(je);
            MessageDigest md5 = MessageDigest.getInstance("MD5");
            byte[] buf = new byte[4096];
            int l, n = 0;
            while ((l = ins.read(buf)) != -1) {
                md5.update(buf, 0, l);
                n += l;
            }
            ins.close();
            jarFile.close();

            JSONObject result = new JSONObject();
            result.put("size", n);
            result.put("time", je.getTime());
            result.put("crc", je.getCrc());
            result.put("md5", byteArrayToHex(md5.digest()));

            response.setStatusCode(200);
            response.setContentTypeJson();
            response.write(result.toString().getBytes("utf-8"));
            return;
        }

        if (path.startsWith("/fileraw/")) {
            ApplicationInfo ai = app.getApplicationInfo();
            File apkFile = new File(ai.sourceDir);

            // 从jarFile中读取raw数据
            JarFile jarFile = new JarFile(apkFile);
            JarEntry je = jarFile.getJarEntry(path.substring("/fileraw/".length()));
            InputStream ins = jarFile.getInputStream(je);

            response.setStatusCode(200);
            response.setContentTypeBinary();
            byte[] buf = new byte[4096];
            int l;
            while ((l = ins.read(buf)) != -1) {
                response.write(buf, 0, l);
            }
            return;
        }
        super.handle(method, path, headers, input, response);
    }

    private static LcastServer runningServer;

    public static void start(Context ctx) {
        if (runningServer != null) {
            Log.d("lcast", "lcast server is already running");
            return;
        }

        // 如何启动一个Server呢?
        // 在指定的返回内监听端口
        for (int i = 0; i < 100; i++) {
            LcastServer s = new LcastServer(ctx, PORT_FROM + i);
            try {
                s.start();
                runningServer = s;
                Log.d("lcast", "lcast server running on port " + (PORT_FROM + i));
                break;
            } catch (Exception e) {
            }
        }
    }

    // 删除: lcast内的所有的apk文件
    public static void cleanCache(Context ctx) {
        File dir = new File(ctx.getCacheDir(), "lcast");
        File[] fs = dir.listFiles();
        if (fs != null) {
            for (File f : fs) {
                rm(f);
            }
        }
    }

    // 递归删除文件其中的apk文件
    //
    private static void rm(File f) {
        if (f.isDirectory()) {
            for (File ff : f.listFiles()) {
                rm(ff);
            }
            f.delete();
        } else if (f.getName().endsWith(".apk")) {
            f.delete();
        }
    }

    private static String byteArrayToHex(byte[] a) {
        StringBuilder sb = new StringBuilder(a.length * 2);
        for (byte b : a)
            sb.append(String.format("%02x", b & 0xff));
        return sb.toString();
    }

}
