# 보충 라이선스 원문 출처

이 파일들은 2026-11-01 공식 원작 저장소에서 받아 그대로 보존했습니다. 실제 감사에 사용한 바이트 SHA-256과 적용 런타임 좌표는 `../runtime-dependencies.json`의 `supplemental_notices`에 기록합니다. 라이선스 텍스트를 임의로 바꾸지 않습니다.

- `xz-1.11-COPYING.txt`: [XZ for Java v1.11 COPYING](https://github.com/tukaani-project/xz-java/blob/v1.11/COPYING), `org.tukaani:xz:1.11` / 0BSD.
- `reactive-streams-1.0.3-COPYING.txt`: [Reactive Streams JVM v1.0.3 COPYING](https://github.com/reactive-streams/reactive-streams-jvm/blob/v1.0.3/COPYING), `org.reactivestreams:reactive-streams:1.0.3` / CC0.
- `rxjava-2.2.9-LICENSE.txt`: [RxJava v2.2.9 LICENSE](https://github.com/ReactiveX/RxJava/blob/v2.2.9/LICENSE), `io.reactivex.rxjava2:rxjava:2.2.9` / Apache-2.0.
- `libyuv-LICENSE.txt`: [공식 libyuv LICENSE](https://chromium.googlesource.com/libyuv/libyuv/+/refs/heads/main/LICENSE), `androidx.camera:camera-core:1.5.3` POM이 지정한 추가 BSD 라이선스의 원작 텍스트. 소스 링크는 moving branch이나 **수록된 라이선스 바이트는 SHA-256으로 고정**합니다. 실제 libyuv 코드 버전을 이 문서가 새로 지정하는 것은 아닙니다.

나머지 런타임 고지는 Gradle가 해석한 아티팩트 내부의 `LICENSE`/`NOTICE`를 읽었습니다. 구체적인 아티팩트/내부 경로/해시는 `../runtime-dependencies.json`에 기록합니다.
