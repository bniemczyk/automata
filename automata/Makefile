OPTIMIZATION=-O3
CLANG=clang $(OPTIMIZATION) -Wno-unused-value -emit-llvm
LLC=llc -x86-asm-syntax=intel
CXX=clang++ -frtti -std=c++11 `llvm-config --cppflags --cxxflags` -g $(OPTIMIZATION)
CC=clang -g $(OPTIMIZATION)
LD=clang++ -frtti
LD_FLAGS=`llvm-config --ldflags --libs` $(LDFLAGS) -g $(OPTIMIZATION)
SOURCES=*.py **/*.py *.c *.cc *.h Makefile

all: avmruntime.bc avmjit.so

cscope.out: $(SOURCES)
	cscope -Rb

tags: $(SOURCES)
	ctags $(SOURCES)

test: all
	python -mcProfile -o peid.prof peid.py
	../most-expensive.py peid.prof

avmjit.so: avmjit.o
	$(LD) -shared $^ $(LD_FLAGS) -o $@

asm: avmruntime.s

ll: avmruntime.ll

%.o: %.cc
	$(CXX) $(CXXFLAGS) -c -o $@ $^

%.o: %.c
	$(CC) $(CFLAGS) -c -o $@ $^

%.s: %.bc
	$(LLC) $^

%.bc: %.c
	$(CLANG) -c -o $@ $^
	chmod 644 $@

%.ll: %.bc
	llvm-dis $^

clean:
	rm -f *.o *.bc *.so *.s *.ll *.pyc *.bc.txt *.prof tags
