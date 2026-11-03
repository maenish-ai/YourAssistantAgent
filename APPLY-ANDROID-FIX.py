from pathlib import Path
import sys
root=Path(__file__).resolve().parent
if not (root/'.git').exists():
    print('ERROR: Put this script in the repository root beside .git');sys.exit(1)
p=root/'android/app/src/main/java/ai/maenish/yourassistant/MainActivity.java'
if not p.exists():print('ERROR: MainActivity.java missing');sys.exit(1)
s=p.read_text(encoding='utf-8');original=s

def change(old,new,label):
    global s
    if new in s:
        print('ALREADY FIXED:',label);return
    count=s.count(old)
    if count!=1:raise RuntimeError(f'{label}: expected one matching block, found {count}; no changes saved')
    s=s.replace(old,new,1);print('PATCHED:',label)

change('''                    CharSequence before=status.getText();applyEvents(response);
                    if(android.text.TextUtils.equals(before,status.getText()))status.setText("متصل • التحديث تلقائي أثناء فتح التطبيق.");
                    schedulePoll();''','''                    try {
                        CharSequence before=status.getText();
                        applyEvents(response);
                        if(android.text.TextUtils.equals(before,status.getText()))
                            status.setText("متصل • التحديث تلقائي أثناء فتح التطبيق.");
                    } catch (RuntimeException uiError) {
                        // A malformed event must not crash the entire Android app.
                        android.util.Log.e("YAA-Poll", "Event UI update failed: " + uiError.getClass().getSimpleName());
                        status.setText("حدث خطأ أثناء عرض تحديث من الكمبيوتر. الاتصال ما زال فعالاً.");
                    } finally {
                        schedulePoll();
                    }''','Protect periodic event UI')
change('''            } catch (ApiClient.ApiException e) {
                main.post(() -> {
                    if (!current(requestGeneration)) return;
                    polling = false;
                    if (e.status == 401 || e.status == 403) {''','''            } catch (Exception e) {
                main.post(() -> {
                    if (!current(requestGeneration)) return;
                    polling = false;
                    int httpStatus = e instanceof ApiClient.ApiException ? ((ApiClient.ApiException)e).status : -1;
                    if (httpStatus == 401 || httpStatus == 403) {''','Handle unexpected poll network errors')
change('''                    status.setText(e.getMessage());
                    schedulePoll();
                });
            }
        });
    }

    private void applyEvents''','''                    status.setText(e instanceof ApiClient.ApiException ? e.getMessage() :
                        "تعذر تحديث الأحداث مؤقتاً. سأعيد المحاولة تلقائياً.");
                    schedulePoll();
                });
            }
        });
    }

    private void applyEvents''','Avoid exposing internal poll errors')
change('''            activeTtsEngine=voice.getDefaultEngine();
            configureArabicVoice();
            voice.setOnUtteranceProgressListener''','''            // TTS initialization is asynchronous: voice can be replaced or shut down.
            if (voice == null) return;
            try {
                activeTtsEngine=voice.getDefaultEngine();
                configureArabicVoice();
            } catch (RuntimeException ttsError) {
                android.util.Log.e("YAA-TTS", "Voice setup failed: " + ttsError.getClass().getSimpleName());
                status.setText("الصوت غير متاح حالياً؛ يمكنك استخدام التطبيق نصياً.");
                return;
            }
            voice.setOnUtteranceProgressListener''','Guard async Android TTS setup')
if s!=original:
    p.write_text(s,encoding='utf-8')
print('DONE. GitHub Desktop: Commit to main, Push origin, install NEW APK from Actions.')
