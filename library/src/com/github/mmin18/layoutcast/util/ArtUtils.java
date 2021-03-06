package com.github.mmin18.layoutcast.util;

import android.util.Log;

import java.io.File;
import java.lang.reflect.Array;
import java.lang.reflect.Field;

import dalvik.system.BaseDexClassLoader;
import dalvik.system.DexClassLoader;

/**
 * Created by mmin18 on 8/8/15.
 */
public class ArtUtils {

    public static boolean overrideClassLoader(ClassLoader cl, File dex, File opt) {
        try {
            // 重新定义: Class Loader?
            ClassLoader bootstrap = cl.getParent();

            // 1. 获取第一个 Field: pathList(修改: Accessible)
            Field fPathList = BaseDexClassLoader.class.getDeclaredField("pathList");
            fPathList.setAccessible(true);

            Object pathList = fPathList.get(cl);

            // XXX: ClassLoader: cl.pathList


            // ClassLoader --> Field pathList --> pathList

            // 2. 获取第二个 Field
            Class cDexPathList = bootstrap.loadClass("dalvik.system.DexPathList");
            Field fDexElements = cDexPathList.getDeclaredField("dexElements");
            fDexElements.setAccessible(true);


            Object dexElements = fDexElements.get(pathList);

            // XXX: ClassLoader: cl.pathList.dexElements

            // 加载: dex
            DexClassLoader cl2 = new DexClassLoader(dex.getAbsolutePath(), opt.getAbsolutePath(), null, bootstrap);
            Object pathList2 = fPathList.get(cl2);
            Object dexElements2 = fDexElements.get(pathList2);  // 读取: dexElements
            // 读取: DexClassLoader的: cl2.pathList.dexElements

            // 读取新的: dexElements
            Object element2 = Array.get(dexElements2, 0);
            int n = Array.getLength(dexElements) + 1;


            Object newDexElements = Array.newInstance(fDexElements.getType().getComponentType(), n);
            Array.set(newDexElements, 0, element2);

            // 将: dexElements 拷贝到: newDexElements 后面
            for (int i = 0; i < n - 1; i++) {
                Object element = Array.get(dexElements, i);
                Array.set(newDexElements, i + 1, element);
            }
            // dexElements = [dexElements2[0], dexElements...]

            // 修改系统的: dexElements
            fDexElements.set(pathList, newDexElements);
            return true;
        } catch (Exception e) {
            Log.e("lcast", "fail to override classloader " + cl + " with " + dex, e);
            return false;
        }
    }

}
