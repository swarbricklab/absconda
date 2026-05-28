rule bonus:
    input: "data/{sample}.fq.gz"
    output: "stats/{sample}.txt"
    conda: "../envs/qc.yaml"
    shell: "echo {input} > {output}"
