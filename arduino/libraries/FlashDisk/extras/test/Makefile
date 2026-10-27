CXXFLAGS = -std=c++11 -Wall -Wextra -O1 -Istub -I../../src

test: test_flashdisk
	./test_flashdisk
	./check.sh

test_flashdisk: test_flashdisk.cpp ../../src/*.h stub/*.h
	$(CXX) $(CXXFLAGS) -o $@ $<

clean:
	rm -f test_flashdisk fat12_*.img fsck.log
