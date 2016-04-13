package com.github.mmin18.layoutcast.server;

import java.lang.reflect.Field;

import android.content.res.Resources;

public class IdProfileBuilder {

	private Resources res;

	public IdProfileBuilder(Resources res) {
		this.res = res;
	}

	public String buildIds(Class<?> Rclazz) throws Exception {
		ClassLoader cl = Rclazz.getClassLoader();

		StringBuilder sb = new StringBuilder();
		sb.append("<?xml version=\"1.0\" encoding=\"utf-8\"?>\n");
		sb.append("<resources>\n");
		Class<?> clazz = null;
		try {
			// 注意资源文件的定义:  me.chunyu.ChunyuYuer.R$id
			String n = Rclazz.getName() + "$id";
			clazz = cl.loadClass(n);
		} catch (ClassNotFoundException e) {
		}

		if (clazz != null) {
			buildIds(sb, clazz);
		}
		sb.append("</resources>");

		return sb.toString();
	}

	private void buildIds(StringBuilder out, Class<?> clazz) throws Exception {
		// 统计Ids的最大最小数值
		int start = 0, end = 0;
		for (Field f : clazz.getDeclaredFields()) {
			// 如何导出资源文件呢?
			// Integer类型的数据，静态的，可访问的
			if (Integer.TYPE.equals(f.getType()) && java.lang.reflect.Modifier.isStatic(f.getModifiers()) && java.lang.reflect.Modifier.isPublic(f.getModifiers())) {
				int i = f.getInt(null);
				if ((i & 0x7f000000) == 0x7f000000) {
					if (start == 0 || i < start) {
						start = i;
					}
					if (end == 0 || i > end) {
						end = i;
					}
				}
			}
		}

		// Type
		// EntryName
		for (int i = start; i > 0 && i <= end; i++) {
			out.append("  <item type=\"");
			out.append(res.getResourceTypeName(i));
			out.append("\" name=\"");
			String name = res.getResourceEntryName(i);
			out.append(name);
			out.append("\" />\n");
		}
	}

	public String buildPublic(Class<?> Rclazz) throws Exception {
		ClassLoader cl = Rclazz.getClassLoader();
		String[] types = { "attr", "id", "style", "string", "dimen", "color",
				"array", "drawable", "layout", "anim", "integer", "animator",
				"interpolator", "transition", "raw" };

		StringBuilder sb = new StringBuilder();
		sb.append("<?xml version=\"1.0\" encoding=\"utf-8\"?>\n");
		sb.append("<resources>\n");

		// 处理各类资源
		for (String type : types) {
			Class<?> clazz = null;
			try {
				String n = Rclazz.getName() + "$" + type;
				clazz = cl.loadClass(n);
			} catch (ClassNotFoundException e) {
			}
			if (clazz == null)
				continue;
			buildPublic(sb, clazz, type);
		}
		sb.append("</resources>");

		return sb.toString();
	}

	private void buildPublic(StringBuilder out, Class<?> clazz, String type)
			throws Exception {
		int start = 0, end = 0;
		for (Field f : clazz.getDeclaredFields()) {
			if (Integer.TYPE.equals(f.getType())
					&& java.lang.reflect.Modifier.isStatic(f.getModifiers())
					&& java.lang.reflect.Modifier.isPublic(f.getModifiers())) {
				int i = f.getInt(null);
				if ((i & 0x7f000000) == 0x7f000000) {
					if (start == 0 || i < start) {
						start = i;
					}
					if (end == 0 || i > end) {
						end = i;
					}
				}
			}
		}

		// 每一类资源都有: type， name, id
		for (int i = start; i > 0 && i <= end; i++) {
			out.append("  <public type=\"");
			out.append(res.getResourceTypeName(i));
			out.append("\" name=\"");
			String name = res.getResourceEntryName(i);
			out.append(name);
			out.append("\" id=\"0x");
			out.append(Integer.toHexString(i));
			out.append("\" />\n");
		}
	}

}
