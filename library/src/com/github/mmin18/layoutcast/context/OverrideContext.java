package com.github.mmin18.layoutcast.context;

import android.app.Activity;
import android.app.Application;
import android.content.Context;
import android.content.ContextWrapper;
import android.content.res.AssetManager;
import android.content.res.Resources;
import android.content.res.Resources.Theme;
import android.os.Bundle;
import android.view.ContextThemeWrapper;

import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.Map.Entry;
import java.util.WeakHashMap;

// Context是什么概念呢?
// ContextWrapper又是如何工作的呢?  ContextProxy: 相同的接口
//
public class OverrideContext extends ContextWrapper {

	private static final int STATE_REQUIRE_RECREATE = 5;

	private final Context base;
	private Resources resources;
	private Theme theme;
	private int state;

    // ContextWrapper(Context base)
    // 这里的Context需要进行资源的托管
	protected OverrideContext(Context base, Resources res) {
		super(base);
		this.base = base;
		this.resources = res;
	}

    // AssetManager 的管理
	@Override
	public AssetManager getAssets() {
		return resources == null ? base.getAssets() : resources.getAssets();
	}

    // Resource的管理(似乎Resource没有增量处理，都是全量的?)
	@Override
	public Resources getResources() {
		return resources == null ? base.getResources() : resources;
	}

	@Override
	public Theme getTheme() {
		if (resources == null) {
			return base.getTheme();
		}

        // Theme的级联
		if (theme == null) {
			theme = resources.newTheme();
			theme.setTo(base.getTheme());
		}
		return theme;
	}

	protected void setResources(Resources res) {
        // 替换资源
		if (this.resources != res) {
			this.resources = res;
			this.theme = null;

            // 修改资源之后，
            // TODO:
			this.state = STATE_REQUIRE_RECREATE;
		}
	}

	/**
	 * @param res set null to reset original resources
	 */
	public static OverrideContext override(ContextThemeWrapper orig, Resources res)
			throws Exception {

        // 如何将当前的ContextWrapper override呢?
        // ContextWrapper 本身我们不打算变化，而且还有外部引用
        // 只期待修改被它proxy的对象
        //
		Context base = orig.getBaseContext();
		OverrideContext oc;
		if (base instanceof OverrideContext) {
			oc = (OverrideContext) base;
			oc.setResources(res);
		} else {
			oc = new OverrideContext(base, res);

            // orig.mBase = oc
			Field fBase = ContextWrapper.class.getDeclaredField("mBase");
			fBase.setAccessible(true);
			fBase.set(orig, oc);
		}

        // ContextThemeWrapper ?
        // origin 的真实类型?
        // 将orig.mResources 设置为 null origin.mTheme 设置为 null
        //
		Field fResources = ContextThemeWrapper.class.getDeclaredField("mResources");
		fResources.setAccessible(true);
		fResources.set(orig, null);

		Field fTheme = ContextThemeWrapper.class.getDeclaredField("mTheme");
		fTheme.setAccessible(true);
		fTheme.set(orig, null);

		return oc;
	}

	//
	// Activities
	//
    public static void initApplication(Application app) {
        // 监听App的各种LifeCycle
        app.registerActivityLifecycleCallbacks(lifecycleCallback);
    }

	public static final int ACTIVITY_NONE = 0;
	public static final int ACTIVITY_CREATED = 1;
	public static final int ACTIVITY_STARTED = 2;
	public static final int ACTIVITY_RESUMED = 3;

    // 自己维持一套: activities 的状态
	private static final WeakHashMap<Activity, Integer> activities = new WeakHashMap<Activity, Integer>();
	public static Activity[] getAllActivities() {
		ArrayList<Activity> list = new ArrayList<Activity>();
		for (Entry<Activity, Integer> e : activities.entrySet()) {
			Activity a = e.getKey();
			if (a != null && e.getValue().intValue() > 0) {
				list.add(a);
			}
		}
		return list.toArray(new Activity[list.size()]);
	}

	public static Activity getTopActivity() {
		Activity r = null;
		for (Entry<Activity, Integer> e : activities.entrySet()) {
			Activity a = e.getKey();
			if (a != null && e.getValue().intValue() == ACTIVITY_RESUMED) {
				r = a;
			}
		}
		return r;
	}

	/**
	 * @return
     * 0: no activities<br>
	 * 1: activities has been paused<br>
	 * 2: activities is visible (有Activity可见，才能和cast.py交互)
	 */
	public static int getApplicationState() {
		int createdCount = 0;
		int resumedCount = 0;
		for (Entry<Activity, Integer> e : activities.entrySet()) {
			int i = e.getValue().intValue();
			if (i >= ACTIVITY_CREATED) {
				createdCount++;
			}
			if (i >= ACTIVITY_RESUMED) {
				resumedCount++;
			}
		}
		if (resumedCount > 0) {
			return 2;
		}
		if (createdCount > 0) {
			return 1;
		}
		return 0;
	}

	public static int getActivityState(Activity a) {
		Integer i = activities.get(a);
		if (i == null) {
			return ACTIVITY_NONE;
		} else {
			return i.intValue();
		}
	}

    /**
     *    ACTIVITY_CREATED  ---> ACTIVITY_STARTED ---> ACTIVITY_RESUMED
     *
     */
	private static final Application.ActivityLifecycleCallbacks lifecycleCallback = new Application.ActivityLifecycleCallbacks() {
		@Override
		public void onActivityStopped(Activity activity) {
			activities.put(activity, ACTIVITY_CREATED);
		}

		@Override
		public void onActivityStarted(Activity activity) {
			activities.put(activity, ACTIVITY_STARTED);
		}

		@Override
		public void onActivitySaveInstanceState(Activity activity,
												Bundle outState) {
		}

		@Override
		public void onActivityResumed(Activity activity) {
			activities.put(activity, ACTIVITY_RESUMED);

			checkActivityState(activity);
		}

		@Override
		public void onActivityPaused(Activity activity) {
			activities.put(activity, ACTIVITY_STARTED);
		}

		@Override
		public void onActivityDestroyed(Activity activity) {
            // 不再监管activity
			activities.remove(activity);
		}

		@Override
		public void onActivityCreated(Activity activity,
									  Bundle savedInstanceState) {
            // 只要不是： Started/Resumed, 就是Created
			activities.put(activity, ACTIVITY_CREATED);
		}
	};

	//
	// State
	//
	private static void checkActivityState(Activity activity) {
		if (activity.getBaseContext() instanceof OverrideContext) {
            // 工作逻辑:
            // 我们修改代码资源，一般是为了对TopMost Activity进行Debug
			OverrideContext oc = (OverrideContext) activity.getBaseContext();

            // 如何recreate呢?
            if (oc.state == STATE_REQUIRE_RECREATE) {
                // 重建
				activity.recreate();
			}
		}
	}

	//
	// Global
	//
	private static Resources overrideResources;

	public static void setGlobalResources(Resources res) throws Exception {
		overrideResources = res;

        Exception err = null;
		for (Activity a : getAllActivities()) {
			try {
                // 修改所有的Acitivty的Resources
				override(a, res);
			} catch (Exception e) {
				err = e;
			}
		}
		if (err != null) {
			throw err;
		}

		final Activity a = OverrideContext.getTopActivity();
		if (a != null) {
			a.runOnUiThread(new Runnable() {
				@Override
				public void run() {
                    // 修改资源之后只修改最新的状态
					checkActivityState(a);
				}
			});
		}
	}

	public static OverrideContext overrideDefault(ContextThemeWrapper orig)
			throws Exception {
		return override(orig, overrideResources);
	}
}
