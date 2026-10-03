# CPC Normative Test Vector

Header:

```text
#CPC|1|b64>xz>tar|102039807403856a4369e5127f8d0aba2651f9985d8d7dceb03bf0ed927336aa
```

Expected user files:

```text
cpc-vector/README.txt      17 bytes   4b39e7ff0679cd2e77b6312a235a6bf07cc84208fbde5de1de3221fe429dee0d
cpc-vector/src/hello.txt    6 bytes   5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03
cpc-vector/empty.bin        0 bytes   e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

Expected outer XZ SHA-256:

```text
102039807403856a4369e5127f8d0aba2651f9985d8d7dceb03bf0ed927336aa
```

Expected recipe:

```text
Base64 → XZ/LZMA2 → TAR
```

A CPC reader passes this vector if it:
1. accepts the header;
2. verifies the XZ SHA-256;
3. decompresses the payload;
4. recognizes safe TAR members;
5. recovers the three user files with exact bytes.

The manifest includes both directory entries and all three regular files.
