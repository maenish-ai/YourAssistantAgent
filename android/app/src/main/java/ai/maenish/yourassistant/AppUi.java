package ai.maenish.yourassistant;

import android.app.Activity;
import android.content.Context;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.StateListDrawable;
import android.view.View;
import android.view.ViewGroup;
import android.widget.*;

/** Shared native components. No web page or third-party UI service is involved. */
final class AppUi {
    static final int BG=Color.rgb(12,17,30), PANEL=Color.rgb(23,31,49), BORDER=Color.rgb(44,55,78);
    static final int TEXT=Color.rgb(238,242,255), MUTED=Color.rgb(162,175,201), ACCENT=Color.rgb(113,90,225), GREEN=Color.rgb(92,221,179);
    static int dp(Context c,int value){return Math.round(value*c.getResources().getDisplayMetrics().density);}
    static GradientDrawable shape(int color,int radius){GradientDrawable d=new GradientDrawable();d.setColor(color);d.setCornerRadius(radius);return d;}
    static LinearLayout root(Activity activity){
        activity.getWindow().setStatusBarColor(BG);activity.getWindow().setNavigationBarColor(BG);
        activity.getWindow().getDecorView().setSystemUiVisibility(0);
        LinearLayout root=new LinearLayout(activity);root.setOrientation(LinearLayout.VERTICAL);root.setBackgroundColor(BG);
        root.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        root.setPadding(dp(activity,16),dp(activity,12),dp(activity,16),dp(activity,10));
        root.setOnApplyWindowInsetsListener((v,i)->{v.setPadding(dp(activity,16)+i.getSystemWindowInsetLeft(),dp(activity,12)+i.getSystemWindowInsetTop(),dp(activity,16)+i.getSystemWindowInsetRight(),dp(activity,10)+i.getSystemWindowInsetBottom());return i;});
        activity.setContentView(root);return root;
    }
    static TextView label(Context c,String text,int size,boolean muted){
        TextView v=new TextView(c);v.setText(text);v.setTextSize(size);v.setTextColor(muted?MUTED:TEXT);
        v.setPadding(dp(c,4),dp(c,5),dp(c,4),dp(c,5));v.setLineSpacing(dp(c,2),1);return v;
    }
    static void header(Activity activity,LinearLayout root,String title,String subtitle,boolean back){
        LinearLayout row=new LinearLayout(activity);row.setGravity(android.view.Gravity.CENTER_VERTICAL);
        ImageView icon=new ImageView(activity);icon.setImageResource(R.drawable.brand_mark);
        icon.setBackground(shape(Color.WHITE,dp(activity,14)));icon.setClipToOutline(true);
        row.addView(icon,new LinearLayout.LayoutParams(dp(activity,48),dp(activity,48)));
        LinearLayout words=new LinearLayout(activity);words.setOrientation(LinearLayout.VERTICAL);
        TextView heading=label(activity,title,20,false);heading.setTypeface(null,Typeface.BOLD);words.addView(heading);
        words.addView(label(activity,subtitle,11,true));row.addView(words,new LinearLayout.LayoutParams(0,-2,1));
        if(back)row.addView(button(activity,"رجوع",activity::finish,false),new LinearLayout.LayoutParams(-2,dp(activity,46)));
        root.addView(row,new LinearLayout.LayoutParams(-1,-2));
    }
    static Button button(Context c,String text,Runnable action,boolean primary){
        Button b=new Button(c);b.setText(text);b.setTextSize(13);b.setAllCaps(false);b.setTextColor(TEXT);
        b.setTypeface(null,Typeface.BOLD);b.setMinHeight(dp(c,44));b.setMinimumHeight(dp(c,44));
        b.setPadding(dp(c,12),dp(c,8),dp(c,12),dp(c,8));b.setElevation(dp(c,primary?2:0));
        StateListDrawable colors=new StateListDrawable();colors.addState(new int[]{-android.R.attr.state_enabled},shape(BORDER,dp(c,12)));
        colors.addState(new int[]{android.R.attr.state_pressed},shape(primary?Color.rgb(103,82,224):BORDER,dp(c,12)));
        colors.addState(new int[]{},shape(primary?ACCENT:PANEL,dp(c,12)));b.setBackground(colors);
        b.setOnClickListener(v->action.run());return b;
    }
    static EditText field(Context c,String hint){
        EditText v=new EditText(c);v.setHint(hint);v.setTextColor(TEXT);v.setHintTextColor(MUTED);v.setTextSize(14);
        GradientDrawable bg=shape(PANEL,dp(c,12));bg.setStroke(dp(c,1),BORDER);v.setBackground(bg);
        v.setPadding(dp(c,14),dp(c,12),dp(c,14),dp(c,12));return v;
    }
    static LinearLayout card(Context c){LinearLayout v=new LinearLayout(c);v.setOrientation(LinearLayout.VERTICAL);v.setPadding(dp(c,12),dp(c,10),dp(c,12),dp(c,10));v.setBackground(shape(PANEL,dp(c,18)));return v;}
    static LinearLayout.LayoutParams space(Context c){LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.topMargin=dp(c,10);return p;}
    static String size(long bytes){if(bytes<1024)return bytes+" B";if(bytes<1024*1024)return String.format(java.util.Locale.ROOT,"%.1f KB",bytes/1024.0);return String.format(java.util.Locale.ROOT,"%.1f MB",bytes/(1024.0*1024));}
}
