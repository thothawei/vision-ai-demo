// 這個檔案只是為了讓 docs/erp-integration.md 裡的 C# 範例可以真的 `dotnet build` 驗證語法/型別，
// 不是要跑起來的完整程式（SQL Server 連線字串是假的，實際導入時要換成真的連線字串）。
using System.Net.Http.Json;
using Microsoft.Data.SqlClient;

// 只是讓專案有進入點可以編譯，不是實際執行流程
Console.WriteLine("erp-integration-sample：只用於 dotnet build 驗證範例程式碼語法，不會真的執行輪詢。");

public record VisionInspection(
    int Id, string CreatedAt, string Module, string Verdict,
    string? ReviewVerdict, string? WorkOrder, string? PartNo,
    string? LotNo, string? Station, string Engine, int ElapsedMs
);

public class VisionPollingService
{
    private readonly HttpClient _http;
    private readonly string _connectionString;
    private int _lastId;

    public VisionPollingService(string baseUrl, string apiKey, string connectionString, int startFromId = 0)
    {
        _http = new HttpClient { BaseAddress = new Uri(baseUrl) };
        _http.DefaultRequestHeaders.Add("X-API-Key", apiKey);
        _connectionString = connectionString;
        _lastId = startFromId;
    }

    public async Task PollOnceAsync(CancellationToken ct = default)
    {
        var url = $"/api/inspections?since_id={_lastId}&limit=200";
        var records = await _http.GetFromJsonAsync<List<VisionInspection>>(url, ct)
                      ?? new List<VisionInspection>();
        if (records.Count == 0) return;

        await using var conn = new SqlConnection(_connectionString);
        await conn.OpenAsync(ct);

        foreach (var r in records)
        {
            const string sql = """
                MERGE dbo.QualityInspections AS target
                USING (SELECT @VisionInspectionId AS VisionInspectionId) AS src
                ON target.VisionInspectionId = src.VisionInspectionId
                WHEN MATCHED THEN UPDATE SET
                    AiVerdict = @AiVerdict, FinalVerdict = @FinalVerdict, InspectedAt = @InspectedAt
                WHEN NOT MATCHED THEN INSERT
                    (VisionInspectionId, InspectionModule, AiVerdict, FinalVerdict,
                     WorkOrderNo, PartNo, LotNo, StationCode, InspectedAt)
                VALUES
                    (@VisionInspectionId, @Module, @AiVerdict, @FinalVerdict,
                     @WorkOrder, @PartNo, @LotNo, @Station, @InspectedAt);
                """;
            // 參數化查詢，避免 SQL injection——不要用字串拼接組 SQL
            await using var cmd = new SqlCommand(sql, conn);
            cmd.Parameters.AddWithValue("@VisionInspectionId", r.Id);
            cmd.Parameters.AddWithValue("@Module", r.Module);
            cmd.Parameters.AddWithValue("@AiVerdict", r.Verdict);
            cmd.Parameters.AddWithValue("@FinalVerdict", (object?)r.ReviewVerdict ?? r.Verdict);
            cmd.Parameters.AddWithValue("@WorkOrder", (object?)r.WorkOrder ?? DBNull.Value);
            cmd.Parameters.AddWithValue("@PartNo", (object?)r.PartNo ?? DBNull.Value);
            cmd.Parameters.AddWithValue("@LotNo", (object?)r.LotNo ?? DBNull.Value);
            cmd.Parameters.AddWithValue("@Station", (object?)r.Station ?? DBNull.Value);
            cmd.Parameters.AddWithValue("@InspectedAt", r.CreatedAt);
            await cmd.ExecuteNonQueryAsync(ct);

            _lastId = Math.Max(_lastId, r.Id);
        }
    }
}
