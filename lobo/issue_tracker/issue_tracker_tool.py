from lobo import configuration, nop_driver

issue_tracker_tool = configuration.get_config('driver:issue_tracker')
if issue_tracker_tool == 'jira':
    import jira_tool as issue_tracker_driver
else:
    issue_tracker_driver = nop_driver.NopDriver()

def tool_entry():
    parser = ToolkitBase([issue_tracker_driver.TestConnection,
                          issue_tracker_driver.NewIssue,
                          issue_tracker_driver.CommentIssue,
                          issue_tracker_driver.Search,
                          issue_tracker_driver.StartProgress,
                          issue_tracker_driver.StopProgress,
                          issue_tracker_driver.ResolveIssue,
                          issue_tracker_driver.SendToCR,
                          issue_tracker_driver.SendToQA,
                          issue_tracker_driver.LandIssue,
                          issue_tracker_driver.MarkInRC,
                          issue_tracker_driver.Reopen,
                          issue_tracker_driver.Reject,
                          issue_tracker_driver.AbortIssue,
                          issue_tracker_driver.GetInRC,
                          issue_tracker_driver.GetOpenIssues,
                          issue_tracker_driver.GetIssuesToReview,
                          issue_tracker_driver.GetBlockerBugsToDo])
    parser.parse()


test_connection       = issue_tracker_driver.TestConnection()
new_issue             = issue_tracker_driver.NewIssue()
comment_issue         = issue_tracker_driver.CommentIssue()
start_progress        = issue_tracker_driver.StartProgress()
stop_progress         = issue_tracker_driver.StopProgress()
send_to_cr            = issue_tracker_driver.SendToCR()
send_to_qa            = issue_tracker_driver.SendToQA()
resolve_issue         = issue_tracker_driver.ResolveIssue()
land                  = issue_tracker_driver.LandIssue()
mark_in_rc            = issue_tracker_driver.MarkInRC()
get_in_rc             = issue_tracker_driver.GetInRC()
mark_as_released      = issue_tracker_driver.MarkAsReleased()
reopen                = issue_tracker_driver.Reopen()
reject                = issue_tracker_driver.Reject()
abort                 = issue_tracker_driver.AbortIssue()
search                = issue_tracker_driver.Search()
get_open_issues       = issue_tracker_driver.GetOpenIssues()
get_issues_to_review  = issue_tracker_driver.GetIssuesToReview()
get_blocker_bugs_todo = issue_tracker_driver.GetBlockerBugsToDo()

if __name__ == "__main__":
    tool_entry()
