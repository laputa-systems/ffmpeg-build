#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libavutil/avutil.h>
#include <stdio.h>
#include <string.h>

static int decode_first_frame(const char *path, const char *want_decoder)
{
    AVFormatContext *format = NULL;
    AVCodecContext *codec = NULL;
    AVPacket *packet = av_packet_alloc();
    AVFrame *frame = av_frame_alloc();
    const AVCodec *decoder = NULL;
    int status = 1;

    if (!packet || !frame || avformat_open_input(&format, path, NULL, NULL) < 0 ||
        avformat_find_stream_info(format, NULL) < 0) {
        fprintf(stderr, "cannot open %s\n", path);
        goto done;
    }
    int stream = av_find_best_stream(format, AVMEDIA_TYPE_VIDEO, -1, -1, &decoder, 0);
    if (stream < 0 || !decoder) {
        fprintf(stderr, "no video decoder for %s\n", path);
        goto done;
    }
    if (strcmp(decoder->name, want_decoder) != 0) {
        fprintf(stderr, "%s decoded by %s, want %s\n", path, decoder->name, want_decoder);
        goto done;
    }
    codec = avcodec_alloc_context3(decoder);
    if (!codec || avcodec_parameters_to_context(codec, format->streams[stream]->codecpar) < 0 ||
        avcodec_open2(codec, decoder, NULL) < 0) {
        fprintf(stderr, "cannot open decoder %s\n", decoder->name);
        goto done;
    }
    while (av_read_frame(format, packet) >= 0) {
        if (packet->stream_index == stream && avcodec_send_packet(codec, packet) >= 0 &&
            avcodec_receive_frame(codec, frame) >= 0) {
            printf("decoded %s with %s: %dx%d\n", path, decoder->name, frame->width, frame->height);
            status = 0;
            break;
        }
        av_packet_unref(packet);
    }
    if (status) {
        avcodec_send_packet(codec, NULL);
        if (avcodec_receive_frame(codec, frame) >= 0) {
            printf("decoded %s with %s: %dx%d\n", path, decoder->name, frame->width, frame->height);
            status = 0;
        } else {
            fprintf(stderr, "no frame decoded from %s\n", path);
        }
    }
done:
    av_frame_free(&frame);
    av_packet_free(&packet);
    avcodec_free_context(&codec);
    avformat_close_input(&format);
    return status;
}

int main(int argc, char **argv)
{
    if (argc != 3) {
        fprintf(stderr, "usage: %s <h264.mp4> <av1.mp4>\n", argv[0]);
        return 2;
    }
    printf("libavutil %s\n", av_version_info());
    if (!strstr(avformat_configuration(), "--disable-network")) {
        fprintf(stderr, "configuration lacks --disable-network\n");
        return 1;
    }
    void *opaque = NULL;
    const char *protocol;
    while ((protocol = avio_enum_protocols(&opaque, 0))) {
        if (strcmp(protocol, "file") != 0) {
            fprintf(stderr, "unexpected input protocol %s\n", protocol);
            return 1;
        }
    }
    return decode_first_frame(argv[1], "h264") || decode_first_frame(argv[2], "libdav1d");
}
