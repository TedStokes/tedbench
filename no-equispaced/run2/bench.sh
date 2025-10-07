#!/bin/bash
: > build.log
: > stdout.log
: > stderr.log
: > time.log
: > data.txt
start_build=$(date +%s)
echo "Building: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a data.txt

cd ~/master_nektar++/build
git fetch --all &>> ~/tedbench/no-equispaced/run2/build.log
echo "Checking out ted/master..." &>> ~/tedbench/no-equispaced/run2/build.log
git checkout ted/master &>> ~/tedbench/no-equispaced/run2/build.log
rm CMakeCache.txt &>> ~/tedbench/no-equispaced/run2/build.log
cmake -DNEKTAR_USE_HDF5=ON -DNEKTAR_USE_MPI=ON -DNEKTAR_USE_VTK=ON .. &>> ~/tedbench/no-equispaced/run2/build.log
make install -j100 &>> ~/tedbench/no-equispaced/run2/build.log
cd ~/third_nektar++/build
git fetch --all &>> ~/tedbench/no-equispaced/run2/build.log
echo "Checking out ted/feature/geomfactors-refactor..." &>> ~/tedbench/no-equispaced/run2/build.log
git checkout ted/feature/geomfactors-refactor &>> ~/tedbench/no-equispaced/run2/build.log
rm CMakeCache.txt &>> ~/tedbench/no-equispaced/run2/build.log
cmake -DNEKTAR_USE_HDF5=ON -DNEKTAR_USE_MPI=ON -DNEKTAR_USE_VTK=ON .. &>> ~/tedbench/no-equispaced/run2/build.log
make install -j100 &>> ~/tedbench/no-equispaced/run2/build.log

cd ~/tedbench/no-equispaced/run2
start_bench=$(date +%s)
echo "Building took $((start_bench - start_build))s" | tee -a data.txt
echo "Benchmarking: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a data.txt
for s in 19 32 39 44 48 52 55
do
    cp ~/tedbench/cube_tet_template.geo cube_tet_$s.geo
    sed -i s/size_var/$s/g cube_tet_$s.geo
    gmsh -3 cube_tet_$s.geo >/dev/null
    rm cube_tet_$s.geo
    ~/master_nektar++/build/dist/bin/NekMesh cube_tet_$s.msh cube_tet_$s.xml -f
    rm cube_tet_$s.msh
    let num=$s*$s*$s*6
    echo $s "*" $s "*" $s "* 6 = " $num " tets" | tee -a data.txt

    echo "master" | tee -a data.txt
    /bin/time -v -o tmp_time.log \
      ~/master_nektar++/build/dist/bin/FieldConvert cube_tet_$s.xml cube_tet_$s.vtu -f -v \
      > >(tee -a "stdout.log") \
      2> >(tee -a "stderr.log" >&2) \
      | grep -e "InputXml CPU Time: " -e "OutputVtk CPU Time: " -e "ERROR:" | tee -a data.txt
    cat tmp_time.log >> time.log
    grep -e "Maximum resident set size" tmp_time.log | tee -a data.txt
    rm cube_tet_$s.vtu
    echo "" | tee -a data.txt

    echo "feature/geomfactors-refactor" | tee -a data.txt
    /bin/time -v -o tmp_time.log \
      ~/third_nektar++/build/dist/bin/FieldConvert cube_tet_$s.xml cube_tet_$s.vtu -f -v \
      > >(tee -a "stdout.log") \
      2> >(tee -a "stderr.log" >&2) \
      | grep -e "InputXml CPU Time: " -e "OutputVtk CPU Time: " -e "ERROR:" | tee -a data.txt
    cat tmp_time.log >> time.log
    grep -e "Maximum resident set size" tmp_time.log | tee -a data.txt
    rm cube_tet_$s.vtu
    echo "" | tee -a data.txt

    echo "master no-equispaced" | tee -a data.txt
    /bin/time -v -o tmp_time.log \
      ~/master_nektar++/build/dist/bin/FieldConvert cube_tet_$s.xml cube_tet_$s.vtu --no-equispaced -f -v \
      > >(tee -a "stdout.log") \
      2> >(tee -a "stderr.log" >&2) \
      | grep -e "InputXml CPU Time: " -e "OutputVtk CPU Time: " -e "ERROR:" | tee -a data.txt
    cat tmp_time.log >> time.log
    grep -e "Maximum resident set size" tmp_time.log | tee -a data.txt
    rm cube_tet_$s.vtu
    echo "" | tee -a data.txt

    echo "feature/geomfactors-refactor no-equispaced" | tee -a data.txt
    /bin/time -v -o tmp_time.log \
      ~/third_nektar++/build/dist/bin/FieldConvert cube_tet_$s.xml cube_tet_$s.vtu --no-equispaced -f -v \
      > >(tee -a "stdout.log") \
      2> >(tee -a "stderr.log" >&2) \
      | grep -e "InputXml CPU Time: " -e "OutputVtk CPU Time: " -e "ERROR:" | tee -a data.txt
    cat tmp_time.log >> time.log
    grep -e "Maximum resident set size" tmp_time.log | tee -a data.txt
    rm cube_tet_$s.vtu
    echo "" | tee -a data.txt

    rm cube_tet_$s.xml
    rm tmp_time.log
done
done_bench=$(date +%s)
echo "Benchmarking took $((done_bench - start_bench))s" | tee -a data.txt
echo "Done: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a data.txt