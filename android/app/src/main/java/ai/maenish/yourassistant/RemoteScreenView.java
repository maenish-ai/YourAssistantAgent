package ai.maenish.yourassistant;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Matrix;
import android.graphics.Paint;
import android.graphics.RectF;
import android.view.GestureDetector;
import android.view.MotionEvent;
import android.view.ScaleGestureDetector;
import android.view.View;

/** Pinch zoom and pan affect only the local image; remote input is explicit. */
final class RemoteScreenView extends View {
    interface Input { void send(String action, float x, float y, float endX, float endY, String frame); }
    private final Matrix matrix = new Matrix();
    private final Paint paint = new Paint(Paint.FILTER_BITMAP_FLAG);
    private Bitmap bitmap;
    private String frame = "";
    private final GestureDetector gestures;
    private final ScaleGestureDetector scaling;
    private final Input input;
    boolean dragMode;
    private float zoom = 1, lastX, lastY, downX, downY;
    private boolean moved, multiple;
    private String downFrame;

    RemoteScreenView(Context context, Input input) {
        super(context); this.input = input; setBackgroundColor(0xff111111);
        scaling = new ScaleGestureDetector(context, new ScaleGestureDetector.SimpleOnScaleGestureListener() {
            @Override public boolean onScale(ScaleGestureDetector detector) {
                float next = Math.max(1, Math.min(6, zoom * detector.getScaleFactor()));
                float factor = next / zoom; zoom = next;
                matrix.postScale(factor, factor, detector.getFocusX(), detector.getFocusY());
                invalidate(); return true;
            }
        });
        gestures = new GestureDetector(context, new GestureDetector.SimpleOnGestureListener() {
            @Override public boolean onDown(MotionEvent event) { return true; }
            @Override public boolean onSingleTapConfirmed(MotionEvent event) {
                if (!multiple && !dragMode) dispatch("click", event.getX(), event.getY()); return true;
            }
            @Override public boolean onDoubleTap(MotionEvent event) {
                if (!multiple && !dragMode) dispatch("double_click", event.getX(), event.getY()); return true;
            }
            @Override public void onLongPress(MotionEvent event) {
                if (!multiple && !dragMode && !moved) dispatch("right_click", event.getX(), event.getY());
            }
        });
    }

    void image(Bitmap next, String identifier) {
        boolean reset = bitmap == null || bitmap.getWidth() != next.getWidth() || bitmap.getHeight() != next.getHeight();
        Bitmap previous = bitmap; bitmap = next; frame = identifier;
        if (reset) reset(); else invalidate();
        if (previous != null) previous.recycle();
    }
    void reset() {
        matrix.reset(); zoom = 1;
        if (bitmap != null && getWidth() > 0 && getHeight() > 0) {
            matrix.setRectToRect(new RectF(0,0,bitmap.getWidth(),bitmap.getHeight()),
                    new RectF(0,0,getWidth(),getHeight()), Matrix.ScaleToFit.CENTER);
        }
        invalidate();
    }
    @Override protected void onSizeChanged(int w,int h,int oldW,int oldH) { reset(); }
    @Override protected void onDraw(Canvas canvas) { super.onDraw(canvas); if (bitmap != null) canvas.drawBitmap(bitmap,matrix,paint); }
    private float[] position(float x,float y) {
        if (bitmap == null) return null;
        Matrix inverse = new Matrix(); if (!matrix.invert(inverse)) return null;
        float[] point = {x,y}; inverse.mapPoints(point);
        point[0] /= bitmap.getWidth(); point[1] /= bitmap.getHeight();
        if (point[0]<0 || point[0]>1 || point[1]<0 || point[1]>1) return null;
        return point;
    }
    private void dispatch(String action,float x,float y) {
        float[] point=position(x,y);
        if (point!=null) input.send(action,point[0],point[1],0,0,frame);
    }
    @Override public boolean onTouchEvent(MotionEvent event) {
        scaling.onTouchEvent(event); gestures.onTouchEvent(event);
        if (event.getActionMasked()==MotionEvent.ACTION_DOWN) {
            lastX=downX=event.getX(); lastY=downY=event.getY(); downFrame=frame; moved=false; multiple=false;
        } else if (event.getPointerCount()>1) multiple=true;
        else if (event.getActionMasked()==MotionEvent.ACTION_MOVE) {
            if (Math.abs(event.getX()-downX)+Math.abs(event.getY()-downY)>12) moved=true;
            if (!dragMode && moved && !scaling.isInProgress() && zoom>1) {
                matrix.postTranslate(event.getX()-lastX,event.getY()-lastY); invalidate();
            }
            lastX=event.getX(); lastY=event.getY();
        } else if (event.getActionMasked()==MotionEvent.ACTION_UP && dragMode && !multiple) {
            float[] start=position(downX,downY), end=position(event.getX(),event.getY());
            if(start!=null && end!=null) input.send("drag",start[0],start[1],end[0],end[1],downFrame);
            performClick();
        }
        return true;
    }
    @Override public boolean performClick() { super.performClick(); return true; }
}
