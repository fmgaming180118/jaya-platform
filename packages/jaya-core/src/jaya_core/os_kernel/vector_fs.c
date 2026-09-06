/* vector_fs.c - JAYA OS Vector DB Filesystem */
typedef unsigned char u8;
typedef unsigned int u32;

extern void ata_read_sector(u32 lba, u8 *buffer);
extern void ata_write_sector(u32 lba, const u8 *buffer);

// Memory layout constants
#define SECTOR_SIZE 512
#define MAX_RECORDS 64
#define RECORD_VEC_LEN 64

struct vector_record {
    u32 id;
    float vector[RECORD_VEC_LEN];
    char text[SECTOR_SIZE - sizeof(u32) - (RECORD_VEC_LEN * sizeof(float))];
};

struct vector_record db[MAX_RECORDS];
int record_count = 0;

void vfs_init() {
    u8 sector_buf[SECTOR_SIZE];

    // Read from Hard Disk Sector 1 (Assuming sector 0 is bootloader or partition table)
    ata_read_sector(1, sector_buf);

    // Check if sector 1 has valid VFS magic or data...
    // For now just load logic into DB
    // To keep it simple, we treat each sector starting from LBA 1 as a record

    for (int i = 0; i < MAX_RECORDS; i++) {
        ata_read_sector(i + 1, (u8*)&db[i]);
        if (db[i].id != 0xFFFFFFFF) {
            record_count++;
        }
    }
}

void vfs_write_record(u32 id, float *vec, const char *text) {
    if (record_count >= MAX_RECORDS) return;

    struct vector_record *rec = &db[record_count];
    rec->id = id;

    for(int i=0; i<RECORD_VEC_LEN; i++) {
        rec->vector[i] = vec[i];
    }

    int txt_idx = 0;
    while(text[txt_idx] != '\0' && txt_idx < sizeof(rec->text) - 1) {
        rec->text[txt_idx] = text[txt_idx];
        txt_idx++;
    }
    rec->text[txt_idx] = '\0';

    ata_write_sector(record_count + 1, (u8*)rec);
    record_count++;
}
