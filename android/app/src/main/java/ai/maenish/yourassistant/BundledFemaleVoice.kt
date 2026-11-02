package ai.maenish.yourassistant

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.os.Handler
import com.k2fsa.sherpa.onnx.OfflineTts
import com.k2fsa.sherpa.onnx.OfflineTtsConfig
import com.k2fsa.sherpa.onnx.OfflineTtsModelConfig
import com.k2fsa.sherpa.onnx.OfflineTtsVitsModelConfig
import java.util.concurrent.Executors

/** Offline Piper synthesis on Android. Never sends TTS text or audio to Windows. */
class BundledFemaleVoice(private val context: Context, private val main: Handler,
                         private val listener: Listener) {
    interface Listener {
        fun onStart()
        fun onDone()
        fun onError(reason: String)
    }
    private val worker=Executors.newSingleThreadExecutor()
    @Volatile private var engine: OfflineTts?=null
    @Volatile private var playing: AudioTrack?=null
    @Volatile private var closed=false
    @Volatile private var generation=0
    fun ready(): Boolean=engine!=null
    fun initialize() {
        worker.execute {
            try {
                val dir="voice/arabic-female"
                val vits=OfflineTtsVitsModelConfig(
                    model="$dir/model.onnx", tokens="$dir/tokens.txt",
                    dataDir="$dir/espeak-ng-data")
                val config=OfflineTtsConfig(
                    model=OfflineTtsModelConfig(vits=vits,numThreads=2,debug=false),
                    maxNumSentences=1)
                val created=OfflineTts(assetManager=context.assets,config=config)
                if(closed) created.release() else engine=created
            } catch(t:Throwable) {
                main.post { listener.onError(t.message?:t.javaClass.simpleName) }
            }
        }
    }
    fun speak(text:String) {
        val id=++generation
        worker.execute {
            val tts=engine?:return@execute
            if(closed||id!=generation)return@execute
            try {
                main.post { listener.onStart() }
                val audio=tts.generate(text,sid=0,speed=0.97f)
                if(closed||id!=generation)return@execute
                val track=AudioTrack.Builder()
                    .setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ASSISTANT)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
                    .setAudioFormat(AudioFormat.Builder().setSampleRate(audio.sampleRate)
                        .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                        .setEncoding(AudioFormat.ENCODING_PCM_FLOAT).build())
                    .setBufferSizeInBytes(maxOf(8192,audio.samples.size*4))
                    .setTransferMode(AudioTrack.MODE_STATIC).build()
                playing=track
                track.write(audio.samples,0,audio.samples.size,AudioTrack.WRITE_BLOCKING)
                track.play()
                // Wait for playback to finish before reopening the microphone.
                val millis=(audio.samples.size*1000L/audio.sampleRate).coerceAtMost(120000)
                val until=System.currentTimeMillis()+millis
                while(!closed&&id==generation&&System.currentTimeMillis()<until)Thread.sleep(35)
                track.stop();track.release();playing=null
            }catch(t:Throwable){main.post { listener.onError(t.message?:"TTS error") }}
            finally{main.post { listener.onDone() }}
        }
    }
    fun stop(){generation++;playing?.pause();playing?.flush()}
    fun close(){closed=true;stop();worker.execute{engine?.release();engine=null};worker.shutdown()}
}
