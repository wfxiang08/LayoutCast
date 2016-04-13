package com.github.mmin18.layoutcast.inflater;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.util.HashMap;

import android.app.Application;
import android.content.Context;
import android.content.ContextWrapper;
import android.util.Log;
import android.view.ContextThemeWrapper;
import android.view.LayoutInflater;

import com.github.mmin18.layoutcast.context.OverrideContext;

/**
 * Used to replace the application service, provide Activity's layout inflater
 * by cloneInContext()
 * 
 * @author mmin18
 */
public class BootInflater extends BaseInflater {

	/**
	 * The original LayoutInflater in Application Service
	 */
	public static LayoutInflater systemInflater;

	public BootInflater(Context context) {
		super(context);
	}

	@Override
	public LayoutInflater cloneInContext(Context newContext) {
		if (newContext instanceof ContextThemeWrapper) {
			// 修改: 默认的 LayoutInflater
			//      也就是在调用的时候设置: Resource等
			try {
				OverrideContext.overrideDefault((ContextThemeWrapper) newContext);
			} catch (Exception e) {
				Log.e("lcast", "fail to override resource in context " + newContext, e);
			}
		}
		return super.cloneInContext(newContext);
	}

	public static void initApplication(Application app) {
		// 1. 修改系统的: InflaterService
		LayoutInflater inflater = (LayoutInflater) app.getSystemService(Context.LAYOUT_INFLATER_SERVICE);
		if (inflater instanceof BootInflater) {
			// already inited
			return;
		}

		// 2.
		systemInflater = inflater;
		Class<?> cCtxImpl = app.getBaseContext().getClass();
		if ("android.app.ContextImpl".equals(cCtxImpl.getName())) {
			ClassLoader cl = cCtxImpl.getClassLoader();
			Class<?> cSer = cCtxImpl; // SystemServiceRegistry after Android 6.0
			boolean androidM = false;
			try {
				cSer = cl.loadClass("android.app.SystemServiceRegistry");
				androidM = true;
			} catch(Exception e) {
			}

			try {
				String fetcherStr = androidM ? "android.app.SystemServiceRegistry$StaticServiceFetcher" : "android.app.ContextImpl$StaticServiceFetcher";
				String fetcherImpl = (androidM ? "android.app.SystemServiceRegistry$" : "android.app.ContextImpl$");
				Class<?> cStaticFetcher = cl.loadClass(fetcherStr);
				Class<?> cFetcherContainer = null;

				// 寻找一个: fetcherImpl
				for (int i = 1; i < 50; i++) {
					String cn = fetcherImpl + i;
					try {
						Class<?> c = cl.loadClass(cn);
						if (cStaticFetcher.isAssignableFrom(c)) {
							cFetcherContainer = c;
							break;
						}
					} catch (Exception e) {
					}
				}
				Constructor<?> cFetcherConstructor = cFetcherContainer.getDeclaredConstructor();
				cFetcherConstructor.setAccessible(true);
				Object fetcher = cFetcherConstructor.newInstance();
				Field f = cStaticFetcher.getDeclaredField("mCachedInstance");
				f.setAccessible(true);
				f.set(fetcher, new BootInflater(app));
				f = cSer.getDeclaredField(androidM ? "SYSTEM_SERVICE_FETCHERS" : "SYSTEM_SERVICE_MAP");
				f.setAccessible(true);

				// 通过反射来修改系统的: InflatorService
				HashMap<String, Object> map = (HashMap<String, Object>) f.get(null);
				map.put(Context.LAYOUT_INFLATER_SERVICE, fetcher);
			} catch (Exception e) {
				throw new RuntimeException("unable to initialize application for BootInflater");
			}
		} else {
			throw new RuntimeException("application base context class "  + cCtxImpl.getName() + " is not expected");
		}

		if (!(app.getSystemService(Context.LAYOUT_INFLATER_SERVICE) instanceof BootInflater)) {
			throw new RuntimeException("unable to initialize application for BootInflater");
		}
	}
}
