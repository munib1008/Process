declare interface IProcessHubWebPartStrings {
  PropertyPaneDescription: string;
  BasicGroupName: string;
  LibraryGroupName: string;
  LibraryFieldLabel: string;
  LibraryFieldHelp: string;
  LibraryInvalid: string;
  UrlFieldLabel: string;
  UrlInvalid: string;
  StartFieldLabel: string;
  StartDashboard: string;
  StartHandbook: string;
  StartLibrary: string;
  StartDepartments: string;
  StartCustom: string;
  CustomFieldLabel: string;
  PageInvalid: string;
  HeightFieldLabel: string;
  SetupTitle: string;
  SetupText: string;
  OpenInBrowser: string;
}

declare module 'ProcessHubWebPartStrings' {
  const strings: IProcessHubWebPartStrings;
  export = strings;
}
